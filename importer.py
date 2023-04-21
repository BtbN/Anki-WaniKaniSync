from anki.importing.noteimp import NoteImporter, ForeignNote, UPDATE_MODE
from aqt import mw

import pathlib, shutil


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

    def __init__(self, collection, model, subjects):
        NoteImporter.__init__(self, collection, None)
        self.allowHTML = True
        self.importMode = UPDATE_MODE
        self.model = model
        self.subjects = subjects

    def fields(self):
        return len(self.FIELDS)

    def foreignNotes(self):
        return [self.makeNote(subj) for subj in self.subjects]

    def makeNote(self, subject):
        data = subject["data"]
        note = ForeignNote()

        meanings = self.get_meanings(subject)
        meanings_whl = self.get_meanings_whl(subject)

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

            "",
            "",
            "",
            "",
            "",
            "",
            "",

            "",
            "",
            "",

            "",
            "",
            "",

            "",
            "",
            "",

            "",
            "",

            ""
        ]

        note.fields = [str(f) for f in note.fields]

        return note

    def get_character(self, subject):
        # TODO: Take care of radicals without characters
        return subject["data"]["characters"]

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


def ensure_notes(col, subjects, note_name, deck_name):
    model = col.models.by_name(note_name)
    if not model:
        raise Exception("Can't ensure non-existant model")
    deck_id = col.decks.id(deck_name, create=False)
    if not deck_id:
        raise Exception("Can't ensure non-existant deck")

    col.set_aux_notetype_config(model["id"], "lastDeck", deck_id)

    importer = WKImporter(col, model, subjects)
    importer.initMapping()
    importer.run()

    return len(subjects) > 0
