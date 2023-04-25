from anki.importing.noteimp import NoteImporter, ForeignNote, UPDATE_MODE
from aqt import mw

import pathlib, shutil
import requests

from .utils import report_progress


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

    def __init__(self, collection, model, subjects, sub_subjects):
        NoteImporter.__init__(self, collection, None)
        self.allowHTML = True
        self.importMode = UPDATE_MODE
        self.model = model
        self.subjects = subjects
        self.sub_subjects = sub_subjects

        self.session = requests.Session()

    def fields(self):
        return len(self.FIELDS) + 1 # Final unnamed field is the _tags one

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

        comp_chars, comp_mean, comp_read = self.get_components(subject, "component_subject_ids")
        simi_chars, simi_mean, simi_read = self.get_components(subject, "visually_similar_subject_ids")
        amal_chars, amal_mean, amal_read = self.get_components(subject, "amalgamation_subject_ids")

        note = ForeignNote()

        note.fields = [
            subject["id"],
            data["level"]*10000 + data["lesson_position"],
            self.get_character(subject),
            subject["object"].capitalize(),
            ", ".join(data["parts_of_speech"]) if "parts_of_speech" in data else "",

            ", ".join(meanings),
            data["meaning_mnemonic"],
            data["meaning_hint"] if "meaning_hint" in data else "",
            ", ".join(meanings_whl + meanings),

            readings.get("primary", "") or "",
            ", ".join(readings.get("onyomi", [])),
            ", ".join(readings.get("kunyomi", [])),
            ", ".join(readings.get("nanori", [])),
            ", ".join(readings.get("accepted", [])),
            data.get("reading_mnemonic", ""),
            data.get("reading_hint", ""),

            ", ".join(comp_chars),
            ", ".join(comp_mean),
            ", ".join(comp_read),

            ", ".join(simi_chars),
            ", ".join(simi_mean),
            ", ".join(simi_read),

            ", ".join(amal_chars),
            ", ".join(amal_mean),
            ", ".join(amal_read),

            "Online; See on Website; <a href=\"" + subject["data"]["document_url"] + "\">" + subject["data"]["document_url"] + "</a>",
            self.get_context_sentences(subject),

            self.ensure_audio(subject),

            "Lesson_" + str(data["level"]) + " " + subject["object"].capitalize()
        ]

        note.fields = [str(f) for f in note.fields]

        return note

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
                if meaning["primary"]:
                    res.insert(0, meaning["meaning"])
                else:
                    res.append(meaning["meaning"])
        return res

    def get_meanings_whl(self, subject):
        aux = subject["data"]["auxiliary_meanings"]
        res = []
        for item in aux:
            if item["type"] == "whitelist":
                res.append(item["meaning"])
        return res

    def get_readings(self, subject):
        readings = subject["data"]["readings"] if "readings" in subject["data"] else []
        res = {
            "primary": "",
            "accepted": []
        }
        for reading in readings:
            if reading["primary"]:
                res["primary"] = reading["reading"]
            if reading["accepted_answer"]:
                res["accepted"].append(reading["reading"])
            if "type" in reading:
                if reading["type"] not in res:
                    res[reading["type"]] = []
                res[reading["type"]].append(reading["reading"])
        return res

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

            chars.append(self.get_character(sub_subj))

            for meaning in sub_subj["data"]["meanings"]:
                if meaning["primary"]:
                    mean.append(meaning["meaning"])
                    break

            if "readings" in sub_subj["data"]:
                for reading in sub_subj["data"]["readings"]:
                    if reading["primary"]:
                        read.append(reading["reading"])
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
        res = ""

        for audio in audios:
            if audio["content_type"] != "audio/mpeg":
                continue
            filename = f'wk3_{audio["metadata"]["source_id"]}.mp3'
            filepath = dest_dir / filename

            if not filepath.exists():
                req = self.session.get(audio["url"])
                req.raise_for_status()
                filepath.write_bytes(req.content)

            res += f"[sound:{filename}]"

        return res



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


def sort_new_cards(col, deck_name):
    card_ids = col.find_cards(f'"deck:{deck_name}" is:new')

    sort_keys = {}
    for cid in card_ids:
        card = col.get_card(cid)
        note = card.note()
        # The Meaning template has the lowest template index(ord), so add it in to have Meaning-Cards first.
        sort_keys[cid] = int(note["sort_id"]) * 100 + card.ord

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


def ensure_notes(col, subjects, sub_subjects, note_name, deck_name):
    model = col.models.by_name(note_name)
    if not model:
        raise Exception("Can't ensure non-existant model")
    deck_id = col.decks.id(deck_name, create=False)
    if not deck_id:
        raise Exception("Can't ensure non-existant deck")

    col.set_aux_notetype_config(model["id"], "lastDeck", deck_id)

    importer = WKImporter(col, model, subjects, sub_subjects)
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
                raise Exception("Matching character has no matching card type!")

            note["card_id"] = str(tps[ct]["id"])
            changed_notes.append(note)
            continue

        found = False
        for slug in subj_by_slug.keys():
            if slug in note_char:
                ct = note["Card_Type"].lower()
                tps = subj_by_slug[slug]

                if ct not in tps:
                    raise Exception("Matching character has no matching card type!")

                note["card_id"] = str(tps[ct]["id"])
                changed_notes.append(note)
                found = True
                break
        if found:
            continue

        raise Exception("Could not match note to subject: " + note["Characters"] + "/" + note["card_id"])

    col.update_notes(changed_notes)
