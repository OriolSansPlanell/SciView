"""Voice clips: narration and sounds placed on a scene's timeline."""
from __future__ import annotations

from .base import Prop, SceneObject, register

SOUND = "Sound"


@register
class Voice(SceneObject):
    """A recording placed in a scene: it starts with the object and plays until its end.

    It draws nothing; the editor shows its waveform on the timeline, so captions can be lined up with
    what is said, and exports mix it with the soundtrack.
    """

    TYPE, LABEL, ICON, CATEGORY = "voice", "Voice clip", "voice", SOUND
    DESCRIPTION = "Narration or a sound effect: record it in the editor, upload a file, or read captions aloud."
    DEFAULT_ENTER = DEFAULT_EXIT = "none"
    PROPS = [
        Prop("audio", "asset", "", accept="audio", group="Sound", help="WAV, MP3, M4A, OGG or a browser recording"),
        Prop("volume", "number", 1.0, min=0, max=4, step=0.05, group="Sound", animatable=False),
        Prop("trim", "number", 0.0, min=0, step=0.1, group="Sound", animatable=False,
             help="Seconds to skip at the beginning of the recording"),
        Prop("fade_in", "number", 0.0, min=0, max=10, step=0.1, group="Sound", animatable=False),
        Prop("fade_out", "number", 0.0, min=0, max=10, step=0.1, group="Sound", animatable=False),
        Prop("script", "longtext", "", group="Sound",
             help="What is said: used for captions and speaker notes"),
    ]

    @classmethod
    def all_props(cls):
        return list(cls.PROPS)          # no opacity or other look: a clip is not drawn

    def draw(self, cv, ctx, v, st):
        return None
