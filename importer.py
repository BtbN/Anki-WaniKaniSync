from anki.importing.noteimp import NoteImporter, ForeignNote, UPDATE_MODE
from aqt import mw

import pathlib, shutil
import requests
import lzma
import html
import csv
import re
from urllib.parse import unquote

from pyrate_limiter import Duration, RequestRate, Limiter

from .utils import report_progress, show_tooltip
from .wk_ctx_parser import WKContextParser


class WKImporter(NoteImporter):
    FIELDS = [
        "card_id", "sort_id", "Characters", "Card_Type", "Word_Type",
        "Meaning", "Meaning_Mnemonic", "Meaning_Hint", "Meaning_Whitelist",
        "Reading", "Reading_Onyomi", "Reading_Kunyomi", "Reading_Nanori", "Reading_Whitelist", "Reading_Mnemonic", "Reading_Hint",
        "Components_Characters", "Components_Meaning", "Components_Reading",
        "Similar_Characters", "Similar_Meaning", "Similar_Reading",
        "Found_in_Characters", "Found_in_Meaning", "Found_in_Reading",
        "Context_Patterns", "Context_Sentences",
        "Audio"
    ]

    def __init__(self, collection, model, subjects, sub_subjects, study_mats):
        NoteImporter.__init__(self, collection, None)
        self.allowHTML = True
        self.importMode = UPDATE_MODE
        self.model = model
        self.subjects = subjects
        self.sub_subjects = sub_subjects
        self.study_mats = study_mats

        self.session = requests.Session()
        self.limiter = Limiter(RequestRate(100, Duration.MINUTE))

        self.pitch_data = self.load_pitch_data()

        config = mw.addonManager.getConfig(__name__)
        self.fetch_patterns = config["FETCH_CONTEXT_PATTERNS"]

    def fields(self):
        return len(self.FIELDS) + 1 # Final unnamed field is the _tags one

    def load_pitch_data(self):
        pitchfile = pathlib.Path(__file__).parent.resolve() / "pitch" / "accent_data.csv.xz"
        res = {}
        with pitchfile.open("rb") as fc:
            with lzma.open(fc, mode="rt", encoding="utf-8", newline='') as f:
                reader = csv.reader(f, delimiter=",")
                for row in reader:
                    orths = row[0].split("|")

                    hiras = row[1].split("|")
                    accents = [int(r) for r in row[2].split("|")]
                    if len(hiras) != len(accents) or len(accents) == 0:
                        raise Exception("Invalid accent data")

                    data = list(zip(hiras, accents))
                    full_hira = "".join(hiras)

                    for orth in orths:
                        for d in data:
                            id = f"{orth}|{d[0]}"
                            if id in res:
                                continue
                            res[id] = [d]

                        id = f"{orth}|{full_hira}"
                        if id in res:
                            continue
                        res[id] = data

        return res

    def foreignNotes(self):
        res = []
        i = 0
        for subj in self.subjects:
            i += 1
            report_progress(f"Importing subject {i}/{len(self.subjects)}...", i, len(self.subjects))
            note = self.makeNote(subj)
            if note:
                res.append(note)
        return res

    def makeNote(self, subject):
        data = subject["data"]
        if data["hidden_at"]:
            return None

        meanings = self.get_meanings(subject)
        meanings_whl = self.get_meanings_whl(subject)

        readings = self.get_readings(subject)

        meaning_synonyms, meaning_note, reading_note = self.get_user_study(subject)

        comp_chars, comp_mean, comp_read = self.get_components(subject, "component_subject_ids")
        simi_chars, simi_mean, simi_read = self.get_components(subject, "visually_similar_subject_ids")
        amal_chars, amal_mean, amal_read = self.get_components(subject, "amalgamation_subject_ids")

        note = ForeignNote()

        note.fields = [
            subject["id"],
            self.get_sort_id(subject),
            f'<a href="{data["document_url"]}">{self.get_character(subject)}</a>',
            subject["object"].replace("_", " ").title(),
            ", ".join(data["parts_of_speech"]) if "parts_of_speech" in data else "",

            ", ".join(meanings),
            self.html_newlines(((data.get("meaning_mnemonic", "") or "") + meaning_note).strip()),
            self.html_newlines(data.get("meaning_hint", "") or ""),
            ", ".join(meanings_whl + meanings + meaning_synonyms),

            ", ".join(readings.get("primary", [])),
            ", ".join(readings.get("onyomi", [])),
            ", ".join(readings.get("kunyomi", [])),
            ", ".join(readings.get("nanori", [])),
            ", ".join(readings.get("accepted", [])),
            self.html_newlines(((data.get("reading_mnemonic", "") or "") + reading_note).strip()),
            self.html_newlines(data.get("reading_hint", "") or ""),

            ", ".join(comp_chars),
            ", ".join(comp_mean),
            ", ".join(comp_read),

            ", ".join(simi_chars),
            ", ".join(simi_mean),
            ", ".join(simi_read),

            ", ".join(amal_chars),
            ", ".join(amal_mean),
            ", ".join(amal_read),

            self.get_context_patterns(subject),
            self.get_context_sentences(subject),

            self.ensure_audio(subject),

            "Lesson_" + str(data["level"]) + " " + subject["object"].title()
        ]

        note.fields = [str(f) for f in note.fields]

        return note

    def get_user_study(self, subject):
        study_mat = self.study_mats.get(subject["id"], None)

        meaning_synonyms = study_mat["meaning_synonyms"] if study_mat else []
        meaning_note = study_mat["meaning_note"] if study_mat else None
        reading_note = study_mat["reading_note"] if study_mat else None

        if meaning_note:
            meaning_note = f"<p class=\"explanation\">User Note</p>{meaning_note}"
        else:
            meaning_note = ""

        if reading_note:
            reading_note = f"<p class=\"explanation\">User Note</p>{reading_note}"
        else:
            reading_note = ""

        return meaning_synonyms, meaning_note, reading_note

    def get_sort_id(self, subject):
        data = subject["data"]

        tp = subject["object"].lower()
        tpo = 30000
        if tp == "vocabulary" or tp == "kana_vocabulary":
            tpo = 20000
        elif tp == "kanji":
            tpo = 10000
        elif tp == "radical":
            tpo = 0

        return data["level"]*100000 + tpo + data["lesson_position"]

    def get_character(self, subject):
        res = subject["data"]["characters"]
        if res:
            return res

        if subject["object"] == "radical":
            return f'<i class="radical-{subject["data"]["slug"]}"></i>'

        return "Not found"

    def get_meanings(self, subject):
        meanings = subject["data"]["meanings"]
        res = []
        for meaning in meanings:
            if meaning["accepted_answer"]:
                meaning["meaning"] = meaning["meaning"].strip()
                if meaning["primary"]:
                    res.insert(0, meaning["meaning"])
                else:
                    res.append(meaning["meaning"])
        return res

    def get_context_patterns(self, subject):
        url = subject["data"]["document_url"]
        res = "Online; See on Website; <a href=\"" + url + "\">" + unquote(url) + "</a>"

        if not self.fetch_patterns or subject["object"] == "radical" or subject["object"] == "kanji":
            return res

        try:
            with self.limiter.ratelimit("wk_import", delay=True):
                req = self.session.get(url)
            req.raise_for_status()

            parser = WKContextParser()
            parser.feed(req.text)

            for id in parser.patterns.keys():
                res += "|" + parser.patterns[id]
                for collo in parser.collos[id]:
                    res += ";" + collo[0] + ";" + collo[1]
        except Exception as e:
            print("Failed parsing context: " + repr(e))

        return res

    def get_meanings_whl(self, subject):
        aux = subject["data"]["auxiliary_meanings"]
        res = []
        for item in aux:
            if item["type"] == "whitelist":
                res.append(item["meaning"].strip())
        return res

    def get_readings(self, subject):
        readings = subject["data"]["readings"] if "readings" in subject["data"] else []
        res = {
            "primary": [],
            "accepted": []
        }
        for reading in readings:
            cur_reading = self.apply_pitch_pattern(subject, reading["reading"].strip())
            if reading["accepted_answer"] and subject["object"] != "kanji":
                if reading["primary"]:
                    txt = f'<reading>{cur_reading}</reading>'
                else:
                    txt = cur_reading
                res["primary"].append(txt)
            if reading["accepted_answer"]:
                res["accepted"].append(cur_reading)
            if "type" in reading:
                if reading["type"] not in res:
                    res[reading["type"]] = []
                if reading["primary"]:
                    txt = f'<reading>{cur_reading}</reading>'
                else:
                    txt = cur_reading
                res[reading["type"]].append(txt)
        return res

    def apply_pitch_internal(self, reading, accent):
        mora = re.findall(r".[ょゃゅョャュ]?", reading)
        if accent <= 0:
            end = "".join(mora[1:])
            res = f'<span class="mora-l-h">{mora[0]}</span><span class="mora-h">{end}</span>'
        elif accent == 1:
            end = "".join(mora[1:])
            res = f'<span class="mora-h-l">{mora[0]}</span><span class="mora-l">{end}</span>'
        else:
            mid = "".join(mora[1:accent])
            end = "".join(mora[accent:])
            res = f'<span class="mora-l-h">{mora[0]}</span><span class="mora-h-l">{mid}</span>'
            if end:
                res += f'<span class="mora-l">{end}</span>'
        return res

    def apply_pitch_pattern(self, subject, reading):
        if subject["object"] == "radical" or subject["object"] == "kanji":
            return reading

        id = subject["data"]["characters"] + "|" + reading
        if id not in self.pitch_data:
            return reading

        res = ""
        for part in self.pitch_data[id]:
            res += self.apply_pitch_internal(part[0], part[1])

        if not res:
            raise Exception(html.escape(f'Invalid pitch output for {id}: {repr(self.pitch_data[id])}'))

        return f'<span class="mora">{res}</span>'

    def get_components(self, subject, type):
        if type not in subject["data"]:
            return [], [], []

        chars = []
        mean = []
        read = []

        sub_ids = subject["data"][type]
        for sub_id in sub_ids:
            if sub_id not in self.sub_subjects:
                continue
            sub_subj = self.sub_subjects[sub_id]

            url = sub_subj["data"]["document_url"]
            char = self.get_character(sub_subj)
            chars.append(f'<a href="{url}">{char}</a>')

            for meaning in sub_subj["data"]["meanings"]:
                if meaning["primary"]:
                    mean.append(meaning["meaning"])
                    break

            if "readings" in sub_subj["data"]:
                for reading in sub_subj["data"]["readings"]:
                    if reading["primary"]:
                        read.append(self.apply_pitch_pattern(sub_subj, reading["reading"].strip()))
                        break
            else:
                read.append("")

        return chars, mean, read

    def get_context_sentences(self, subject):
        if "context_sentences" not in subject["data"]:
            return ""

        res = []
        for stc in subject["data"]["context_sentences"]:
            res.append(stc["en"] + "|" + stc["ja"])
        return "|".join(res)

    def ensure_audio(self, subject):
        if "pronunciation_audios" not in subject["data"]:
            return ""

        dest_dir = pathlib.Path(self.col.media.dir())
        audios = subject["data"]["pronunciation_audios"]
        readings = subject["data"].get("readings", [])
        res = ""

        def audio_sort(audio):
            for i in range(0, len(readings)):
                if readings[i]["reading"] == audio["metadata"]["pronunciation"]:
                    return 1000 + (i*1000) + audio["metadata"]["voice_actor_id"]
            return audio["metadata"]["voice_actor_id"]

        for audio in sorted(audios, key=audio_sort):
            if audio["content_type"] != "audio/mpeg":
                continue
            filename = f'wk3_{audio["metadata"]["source_id"]}.mp3'
            filepath = dest_dir / filename

            if not filepath.exists():
                with self.limiter.ratelimit("wk_import", delay=True):
                    req = self.session.get(audio["url"])
                req.raise_for_status()
                filepath.write_bytes(req.content)

            res += f"[sound:{filename}]"

        return res

    def html_newlines(self, inp):
        return inp.replace("\r", "").replace("\n", "<br/>")



def ensure_deck(col, note_name, deck_name):
    datadir = pathlib.Path(__file__).parent.resolve() / "data"

    source_dir = datadir / "files"
    dest_dir = pathlib.Path(col.media.dir())
    for source_file in source_dir.iterdir():
        dest_file = dest_dir / source_file.name
        if not dest_file.exists():
            shutil.copy(source_file, dest_file)

    ret = False

    model = col.models.by_name(note_name)
    if not model:
        model = col.models.new(note_name)

        for field in WKImporter.FIELDS:
            col.models.add_field(model, col.models.new_field(field))

        col.models.set_sort_index(model, 2)

        # Meaning has to be first, for sorting!
        meaning_tpl = col.models.new_template("Meaning")
        meaning_tpl["qfmt"] = (datadir / "meaning_front.html").read_text(encoding="utf-8")
        meaning_tpl["afmt"] = (datadir / "meaning_back.html").read_text(encoding="utf-8")
        col.models.add_template(model, meaning_tpl)

        reading_tpl = col.models.new_template("Reading")
        reading_tpl["qfmt"] = (datadir / "reading_front.html").read_text(encoding="utf-8")
        reading_tpl["afmt"] = (datadir / "reading_back.html").read_text(encoding="utf-8")
        col.models.add_template(model, reading_tpl)

        model["css"] = (datadir / "style.css").read_text(encoding="utf-8")

        col.models.add_dict(model)
        model = col.models.by_name(note_name)

        ret = True
    else:
        field_names = col.models.field_names(model)
        if field_names != WKImporter.FIELDS:
            raise Exception("Existing WaniKani deck does not match expected field layout!")

    deck_id = col.decks.id(deck_name, create=False)
    if not deck_id:
        deck_id = col.decks.id(deck_name, create=True)
        deck = col.decks.get(deck_id)
        deck["mid"] = model["id"]
        col.decks.save(deck)

        model["did"] = deck_id
        col.models.update_dict(model)

        ret = True

    return ret


def do_update_html():
    datadir = pathlib.Path(__file__).parent.resolve() / "data"
    config = mw.addonManager.getConfig(__name__)

    model = mw.col.models.by_name(config["NOTE_TYPE_NAME"])
    if not model:
        show_tooltip("WaniKani note type not found.")
        return

    model["css"] = (datadir / "style.css").read_text(encoding="utf-8")

    for tmpl in model["tmpls"]:
        if tmpl["name"].lower() == "meaning":
            tmpl["qfmt"] = (datadir / "meaning_front.html").read_text(encoding="utf-8")
            tmpl["afmt"] = (datadir / "meaning_back.html").read_text(encoding="utf-8")
        elif tmpl["name"].lower() == "reading":
            tmpl["qfmt"] = (datadir / "reading_front.html").read_text(encoding="utf-8")
            tmpl["afmt"] = (datadir / "reading_back.html").read_text(encoding="utf-8")
        else:
            show_tooltip("Unknown template name in note type.")
            return

    mw.col.models.update_dict(model)


def sort_new_cards(col, deck_name):
    card_ids = col.find_cards(f'"deck:{deck_name}" is:new')

    sort_keys = {}
    for cid in card_ids:
        card = col.get_card(cid)
        note = card.note()

        tp = note["Card_Type"].lower()
        tpo = 30
        if tp == "vocabulary" or tp == "kana vocabulary":
            tpo = 20
        elif tp == "kanji":
            tpo = 10
        elif tp == "radical":
            tpo = 0

        # The Meaning template has the lowest template index(ord), so add it in to have Meaning-Cards first.
        sort_keys[cid] = int(note["sort_id"]) * 1000 + tpo + card.ord

    card_ids = sorted(card_ids, key=lambda cid: sort_keys[cid])

    col.sched.reposition_new_cards(
        card_ids=card_ids,
        starting_from=0,
        step_size=1,
        randomize=False,
        shift_existing=False
    )


def suspend_hidden_notes(col, subjects, note_name):
    for subject in subjects:
        if not subject["data"]["hidden_at"]:
            continue

        subject_id = subject["id"]
        note_ids = col.find_notes(f'-is:suspended "note:{note_name}" card\\_id:{subject_id}')
        if len(note_ids) > 1:
            print("Found more than one note for a subject id!")

        if len(note_ids):
            col.sched.suspend_notes(note_ids)


def ensure_notes(col, subjects, sub_subjects, study_mats, note_name, deck_name):
    model = col.models.by_name(note_name)
    if not model:
        raise Exception("Can't ensure non-existant model")
    deck_id = col.decks.id(deck_name, create=False)
    if not deck_id:
        raise Exception("Can't ensure non-existant deck")

    col.set_aux_notetype_config(model["id"], "lastDeck", deck_id)

    importer = WKImporter(col, model, subjects, sub_subjects, study_mats)
    importer.initMapping()
    importer.run()

    report_progress("Suspending hidden subjects...", 100, 100)
    suspend_hidden_notes(col, subjects, note_name)

    return len(subjects) > 0


def convert_wk3_notes(col, subjects, note_name):
    model = col.models.by_name(note_name)
    if not model:
        raise Exception("Can't convert non-existant model")

    subj_by_char = {}
    subj_by_slug = {}
    for subj in subjects:
        char = subj["data"]["characters"]
        if char:
            if char not in subj_by_char:
                subj_by_char[char] = {}
            subj_by_char[char][subj["object"]] = subj

        # Only radicals potentially have no characters.
        if subj["object"] != "radical":
            continue

        slug = subj["data"]["slug"]
        if slug not in subj_by_slug:
            subj_by_slug[slug] = {}
        subj_by_slug[slug][subj["object"]] = subj

    note_ids = col.find_notes(f'"note:{note_name}"')
    if not note_ids:
        raise Exception("No notes found, can't convert.")

    changed_notes = []
    suspend_ids = []
    processed_subs = {}
    i = 0
    for note_id in note_ids:
        note = col.get_note(note_id)
        i += 1

        report_progress(f"Converting note {i}/{len(note_ids)}...", i, len(note_ids))

        note_char = note["Characters"].strip()
        if note_char in subj_by_char:
            ct = note["Card_Type"].lower()
            tps = subj_by_char[note_char]

            if ct not in tps:
                print(f"Matching character '{note_char}' has no matching card type: {ct} not in {repr(tps.keys())}")
            else:
                id = tps[ct]["id"]
                if id in processed_subs:
                    raise Exception(f"Duplicate match detected for: {id} {tps[ct]['object']} {html.escape(note_char)} vs. {html.escape(processed_subs[id]['Characters'])}")
                processed_subs[id] = note

                note["card_id"] = str(id)
                changed_notes.append(note)
                continue

        found = False
        for slug in subj_by_slug.keys():
            if f'"radical-{slug}"' in note_char:
                ct = note["Card_Type"].lower()
                tps = subj_by_slug[slug]

                if ct not in tps:
                    print(f"Matching slug '{note_char}' has no matching card type: {ct} not in {repr(tps.keys())}")
                else:
                    id = tps[ct]["id"]
                    if id in processed_subs:
                        raise Exception(f"Duplicate slug match detected for: {id} {tps[ct]['object']} {html.escape(note_char)} vs. {html.escape(processed_subs[id]['Characters'])}")
                    processed_subs[id] = note

                    note["card_id"] = str(id)
                    changed_notes.append(note)
                    found = True
                    break
        if found:
            continue

        print("Could not match note to subject, suspending: " + note["Characters"] + "/" + note["card_id"])
        suspend_ids.append(note_id)

    col.update_notes(changed_notes)
    if suspend_ids:
        col.sched.suspend_notes(suspend_ids)
