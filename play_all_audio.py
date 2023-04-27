from anki.hooks import wrap
from aqt.main import AnkiQt

import aqt.sound as aqt_sound
import aqt.browser.previewer as aqt_previewer
import aqt.reviewer as aqt_reviewer
import aqt.clayout as aqt_clayout


def my_play_clicked_audio(pycmd, card, _old):
    play, context, str_idx = pycmd.split(":")

    if str_idx == "all":
        if context == "q":
            tags = card.question_av_tags()
        else:
            tags = card.answer_av_tags()

        aqt_sound.av_player.play_tags(tags)
    else:
        return _old(pycmd, card)


def leave_marker(self, text, _old):
    text = _old(self, text)
    text = text.replace("__IS_PLAY_ALL_AVAILABLE__", "__YES_IT_IS__")
    return text


def install_play_all_audio():
    aqt_sound.play_clicked_audio = wrap(aqt_sound.play_clicked_audio, my_play_clicked_audio, "around")
    aqt_previewer.play_clicked_audio = aqt_sound.play_clicked_audio
    aqt_reviewer.play_clicked_audio = aqt_sound.play_clicked_audio
    aqt_clayout.play_clicked_audio = aqt_sound.play_clicked_audio    

    AnkiQt.prepare_card_text_for_display = wrap(AnkiQt.prepare_card_text_for_display, leave_marker, "around")
