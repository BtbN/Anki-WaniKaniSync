from anki.importing.noteimp  import NoteImporter, ForeignNote
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

    def __init__(self, *args, **kwargs):
        NoteImporter.__init__(self, *args, **kwargs)


def ensure_deck(note_name, deck_name):
    datadir = pathlib.Path(__file__).parent.resolve() / "data"

    source_dir = datadir / "files"
    dest_dir = pathlib.Path(mw.col.media.dir())
    for source_file in source_dir.iterdir():
        dest_file = dest_dir / source_file.name
        if not dest_file.exists():
            shutil.copy(source_file, dest_file)

    model = mw.col.models.by_name(note_name)
    if not model:
        model = mw.col.models.new(note_name)

        for field in WKImporter.FIELDS:
            mw.col.models.add_field(model, mw.col.models.new_field(field))

        mw.col.models.set_sort_index(model, 2)

        meaning_tpl = mw.col.models.new_template("Meaning")
        meaning_tpl["qfmt"] = (datadir / "meaning_front.html").read_text(encoding="utf-8")
        meaning_tpl["afmt"] = (datadir / "meaning_back.html").read_text(encoding="utf-8")
        mw.col.models.add_template(model, meaning_tpl)

        reading_tpl = mw.col.models.new_template("Reading")
        reading_tpl["qfmt"] = (datadir / "reading_front.html").read_text(encoding="utf-8")
        reading_tpl["afmt"] = (datadir / "reading_back.html").read_text(encoding="utf-8")
        mw.col.models.add_template(model, reading_tpl)

        model["css"] = (datadir / "style.css").read_text(encoding="utf-8")

        mw.col.models.add_dict(model)
        model = mw.col.models.by_name(note_name)

    deck_id = mw.col.decks.id(deck_name, create=False)
    if not deck_id:
        deck_id = mw.col.decks.id(deck_name, create=True)
        deck = mw.col.decks.get(deck_id)
        deck["mid"] = model["id"]
        mw.col.decks.save(deck)

        model["did"] = deck_id
        mw.col.models.update_dict(model)



def ensure_cards(subjects):
    pass