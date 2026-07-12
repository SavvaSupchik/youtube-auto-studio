"""ORM-модели. Импорт здесь регистрирует их в Base.metadata."""
from app.models.project import Project
from app.models.video import Video
from app.models.script import Script
from app.models.script_analysis import ScriptAnalysis
from app.models.audio import AudioTrack
from app.models.video_asset import VideoAsset
from app.models.generation_log import GenerationLog
from app.models.voice import Voice
from app.models.music_track import MusicTrack
from app.models.niche_report import NicheReport

__all__ = [
    "Project",
    "Video",
    "Script",
    "ScriptAnalysis",
    "AudioTrack",
    "VideoAsset",
    "GenerationLog",
    "Voice",
    "MusicTrack",
    "NicheReport",
]
