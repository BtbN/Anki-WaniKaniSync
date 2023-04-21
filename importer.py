from anki.importing.noteimp import NoteImporter, ForeignNote, UPDATE_MODE
from aqt import mw

import pathlib, shutil
import requests


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

    def fields(self):
        return len(self.FIELDS) + 1 # Final unnamed field is the _tags one

    def foreignNotes(self):
        return [self.makeNote(subj) for subj in self.subjects]

    def makeNote(self, subject):
        data = subject["data"]
        note = ForeignNote()

        meanings = self.get_meanings(subject)
        meanings_whl = self.get_meanings_whl(subject)

        readings = self.get_readings(subject)

        comp_chars, comp_mean, comp_read = self.get_components(subject, "component_subject_ids")
        simi_chars, simi_mean, simi_read = self.get_components(subject, "visually_similar_subject_ids")
        amal_chars, amal_mean, amal_read = self.get_components(subject, "amalgamation_subject_ids")

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
            readings.get("onyomi", "") or "",
            readings.get("kunyomi", "") or "",
            readings.get("nanori", "") or "",
            readings.get("accepted", "") or "",
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

            "",

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
    sort_keys = {cid: int(col.get_card(cid).note()["sort_id"]) for cid in card_ids}

    card_ids = sorted(card_ids, key=lambda cid: sort_keys[cid])

    col.sched.reposition_new_cards(
        card_ids=card_ids,
        starting_from=0,
        step_size=1,
        randomize=False,
        shift_existing=False
    )


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

    sort_new_cards(col, deck_name)

    return len(subjects) > 0
