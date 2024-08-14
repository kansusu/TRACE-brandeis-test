import os
import wave
from collections import defaultdict, deque
from pathlib import Path
from typing import final

from silero_vad import get_speech_timestamps, load_silero_vad, read_audio

from mmdemo.base_feature import BaseFeature
from mmdemo.base_interface import BaseInterface
from mmdemo.interfaces import AudioFileInterface, ColorImageInterface


@final
class MicAudio(BaseFeature):
    def initialize(self):
        pass

    def finalize(self):
        pass

    def get_output(self) -> AudioFileInterface | None:
        pass


@final
class RecordedAudio(BaseFeature):
    def __init__(self, *, path: Path) -> None:
        super().__init__()
        self.path = path

    def initialize(self):
        pass

    def finalize(self):
        pass

    def get_output(self) -> AudioFileInterface | None:
        pass


@final
class VADUtteranceBuilder(BaseFeature):
    """
    Input features can be any number of features which output
    `AudioFileInterface`. Each input feature must stay consistent in the format
    of input (rate, channels, etc.).

    Output feature is `AudioFileInterface`.

    Keyword arguments:
    `delete_input_files` -- True if input audio files should be deleted, default True
    `max_utterance_time` -- the maximum number of seconds an utterance can be or None
    """

    def __init__(
        self, *args, delete_input_files=True, max_utterance_time: int | None = 5
    ):
        super().__init__(*args)
        self.delete_input_files = delete_input_files
        self.max_utterance_time = max_utterance_time

    def initialize(self):
        self.counter = 0

        self.vad = load_silero_vad()

        self.current_data = defaultdict(bytes)
        self.contains_activity = defaultdict(bool)
        self.starts = defaultdict(float)
        self.total_time = defaultdict(float)

        self.output_dir = Path("chunks")
        os.makedirs(self.output_dir, exist_ok=True)

        self.outputs = deque()

    def get_output(self, *args: AudioFileInterface) -> AudioFileInterface | None:
        for audio_input in args:
            if not audio_input.is_new():
                continue

            # run through vad
            audio = read_audio(str(audio_input.path))
            activity = len(get_speech_timestamps(audio, self.vad)) > 0

            # load frames and params from file
            wave_reader = wave.open(str(audio_input), "rb")
            chunk_n_frames = wave_reader.getnframes()
            chunk_frames = b""
            for _ in range(chunk_n_frames // 1024 + 1):
                chunk_frames += wave_reader.readframes(1024)
            params = wave_reader.getparams()
            wave_reader.close()

            # force output file to be created if the time is too long
            force_output_creation = (
                self.max_utterance_time is not None
                and self.total_time[audio_input.speaker_id] > self.max_utterance_time
            )

            if activity:
                # add to the stored frames

                if len(self.current_data[audio_input.speaker_id]) == 0:
                    # if no data has been stored yet, set the start time
                    self.starts[audio_input.speaker_id] = audio_input.start_time
                    self.total_time[audio_input.speaker_id] = 0

                self.current_data[audio_input.speaker_id] += chunk_frames
                self.total_time[audio_input.speaker_id] += (
                    audio_input.end_time - audio_input.start_time
                )
                self.contains_activity[audio_input.speaker_id] = True

            if not activity or force_output_creation:
                if self.contains_activity[audio_input.speaker_id]:
                    # if we have stored activity, create a new utterance
                    self.create_utterance(audio_input.speaker_id, params)

                # reset to only storing the last chunk
                self.starts[audio_input.speaker_id] = audio_input.start_time
                self.current_data[audio_input.speaker_id] = chunk_frames
                self.total_time[audio_input.speaker_id] = (
                    audio_input.end_time - audio_input.start_time
                )
                self.contains_activity[audio_input.speaker_id] = False

        if len(self.outputs) > 0:
            return self.outputs.popleft()

        return None

    def create_utterance(self, speaker_id, params):
        """
        Create an utterance file based on saved data and add to `self.outputs`
        """
        next_file = self.output_dir / "chunks" / f"{self.counter:08}.wav"
        wf = wave.open(str(next_file), "wb")
        wf.setparams(params)
        wf.writeframes(self.current_data[speaker_id])
        wf.close()

        self.outputs.append(
            AudioFileInterface(
                speaker_id=speaker_id,
                start_time=self.starts[speaker_id],
                end_time=self.starts[speaker_id] + self.total_time[speaker_id],
                path=next_file,
            )
        )

        self.counter += 1
