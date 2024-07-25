"""
Base profile which can be used by the demo to load different devices
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from time import time
from tkinter import Checkbutton, IntVar, Tk

import cv2 as cv

from config import K4A_DIR, PLAYBACK_SKIP_FRAMES, PLAYBACK_TARGET_FPS
from fake_camera import FakeCamera
from featureModules import (AsrFeature, AsrFeatureEval, BaseDevice,
                            CommonGroundFeature, DenseParaphrasingFeature,
                            GazeBodyTrackingFeature, GazeFeature,
                            GestureFeature, GestureFeatureEval, MicDevice,
                            MoveFeature, MoveFeatureEval, ObjectFeature,
                            PoseFeature, PrerecordedDevice, PropExtractFeature,
                            PropExtractFeatureEval, rec_common_ground)
from logger import Logger

# tell the script where to find certain dll's for k4a, cuda, etc.
# body tracking sdk's tools should contain everything
os.add_dll_directory(K4A_DIR)
import azure_kinect


class BaseProfile(ABC):
    def __init__(
            self,
            eval_dir=None,
            eval_asr=False,
            eval_prop=False,
            eval_gesture=False,
            eval_move=False,
        ) -> None:
        self.output_dir = Path(f"stats_{str(datetime.now().strftime('%Y-%m-%d_%H_%M_%S'))}")
        self.video_dir = self.output_dir / "video_files"
        self.processed_frame_dir = self.output_dir / "processed_frames"
        self.raw_frame_dir = self.output_dir / "raw_frames"
        for i in (self.output_dir, self.video_dir, self.processed_frame_dir, self.raw_frame_dir):
            os.makedirs(i, exist_ok=True)

        self.eval_dir = Path(eval_dir) if eval_dir is not None else None
        self.eval_asr = eval_asr
        self.eval_prop = eval_prop
        self.eval_gesture = eval_gesture
        self.eval_move = eval_move
        if self.eval_asr or self.eval_prop or self.eval_gesture or self.eval_move:
            assert self.eval_dir is not None, "No evaluation directory provided"

    def init_features(self):
        self.root = Tk()
        # self.root.geometry('350x200')
        self.root.title("Output Options")

        self.vars = {
                "gesture": IntVar(value=1),
                "objects": IntVar(value=1),
                "gaze": IntVar(value=1),
                "asr": IntVar(value=1),
                "dense paraphrasing": IntVar(value=1),
                "pose": IntVar(value=0),
                "prop": IntVar(value=1),
                "move": IntVar(value=1),
                "common ground": IntVar(value=1),
                }

        self._create_buttons()

        timestamp_offset = time()

        self.objects = ObjectFeature(log_dir=self.output_dir)

        shift = 7 # TODO what is this?
        self.gaze = GazeBodyTrackingFeature(shift, log_dir=self.output_dir)

        if self.eval_gesture:
            self.gesture = GestureFeatureEval(self.eval_dir, log_dir=self.output_dir)
        else:
            self.gesture = GestureFeature(timestamp_offset, shift, log_dir=self.output_dir)

        self.pose = PoseFeature(log_dir=self.output_dir)

        if self.eval_asr:
            self.asr = AsrFeatureEval(self.eval_dir, chunks_in_input_dir=True, log_dir=self.output_dir)
        else:
            self.asr = AsrFeature(self.create_audio_devices(), timestamp_offset, n_processors=1, log_dir=self.output_dir)

        self.dense_paraphrasing = DenseParaphrasingFeature(log_dir=self.output_dir)

        if self.eval_prop:
            self.prop = PropExtractFeatureEval(self.eval_dir, log_dir=self.output_dir)
        else:
            self.prop = PropExtractFeature(log_dir=self.output_dir)

        if self.eval_move:
            self.move = MoveFeatureEval(self.eval_dir, log_dir=self.output_dir)
        else:
            self.move = MoveFeature(log_dir=self.output_dir)

        self.common_ground = CommonGroundFeature(log_dir=self.output_dir)

        if self.output_dir is not None:
            self.error_log = Logger(file=self.output_dir / "errors.txt", stdout=True)
            self.summary_log = Logger(file=self.output_dir / "summary.txt", stdout=True)
        else:
            self.error_log = Logger(stdout=True)
            self.summary_log = Logger(stdout=True)

        self.error_log.clear()
        self.summary_log.clear()

    def _create_buttons(self):
        for text,var in self.vars.items():
            Checkbutton(self.root, text=text, variable=var, onvalue=1, offvalue=0, height=2, width=10).pack()

    def _should_process(self, var):
        return self.vars[var].get()

    def processFrame(self, output_frame, framergb, depth, bodies, rotation, translation, cameraMatrix, distortion, frame_count):
        device_id = 0
        h,w,_ = output_frame.shape

        self.root.update()

        # run features
        blockStatus = {}
        blocks = []

        if(self._should_process("objects")):
            blocks = self.objects.processFrame(framergb, frame_count)

        if(self._should_process("pose")):
            self.pose.processFrame(bodies, output_frame, frame_count, False)

        try:
            if(self._should_process("gaze")):
                self.gaze.processFrame( bodies, w, h, rotation, translation, cameraMatrix, distortion, output_frame, framergb, depth, blocks, blockStatus, frame_count)
        except:
            pass
        
        if(self._should_process("gesture")):
             self.gesture.processFrame(device_id, bodies, w, h, rotation, translation, cameraMatrix, distortion, output_frame, framergb, depth, blocks, blockStatus, frame_count, False)

        new_utterances = []
        if(self._should_process("asr")):
            new_utterances = self.asr.processFrame(output_frame, frame_count, False)

        if self._should_process("dense paraphrasing"):
            self.dense_paraphrasing.processFrame(output_frame, new_utterances, self.asr.utterance_lookup, self.gesture.blockCache, frame_count)

        try:
            if(self._should_process("prop")):
                self.prop.processFrame(output_frame, new_utterances, self.dense_paraphrasing.paraphrased_utterance_lookup, frame_count, False)
        except Exception as e:
            self.error_log.append(f"Frame {frame_count}\nProp extractor\n{new_utterances}\n{str(e)}\n\n")

        if(self._should_process("move")):
            self.move.processFrame(output_frame, new_utterances, self.dense_paraphrasing.paraphrased_utterance_lookup, frame_count, False)

        if self._should_process("common ground"):
            self.common_ground.processFrame(output_frame, new_utterances, self.prop.prop_lookup, self.move.move_lookup, frame_count)


        cv.putText(output_frame, "FRAME:" + str(frame_count), (50,50), cv.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2, cv.LINE_AA)
        #cv.putText(frame, "DEVICE:" + str(int(device_id)), (50,100), cv.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2, cv.LINE_AA)

        self.update_summary(new_utterances, frame_count)

    def update_summary(self, new_utterances, frame_count):
        for i in new_utterances:
            utterance = self.dense_paraphrasing.paraphrased_utterance_lookup[i]
            prop = self.prop.prop_lookup[i]
            move = self.move.move_lookup[i]

            update = ""
            update += "FRAME: " + str(frame_count) + "\n"
            update += "E bank\n"
            update += str(self.common_ground.closure_rules.ebank) + "\n"
            update += "F bank\n"
            update += str(self.common_ground.closure_rules.fbank) + "\n"
            if prop.prop == "no prop":
                update += f"{utterance.speaker_id}: {utterance.text} ({self.common_ground.most_recent_prop}), {move.move}\n\n"
            else:
                update += f"{utterance.speaker_id}: {utterance.text} => {prop.prop}, {move.move}\n\n"

            self.summary_log.append(update)

    def finalize(self):
        if hasattr(self.asr, "done"):
            self.asr.done.value = True

        self.frames_to_video(
                f"{self.output_dir}\\processed_frames\\frame%8d.png",
                f"{self.video_dir}\\processed_frames.mp4")
        self.frames_to_video(
                f"{self.output_dir}\\raw_frames\\frame%8d.png",
                f"{self.video_dir}\\raw_frames.mp4")

    @staticmethod
    def frames_to_video(frame_path, output_path, rate=PLAYBACK_TARGET_FPS):
        os.system(f"ffmpeg -framerate {rate} -i {frame_path} -c:v libx264 -pix_fmt yuv420p {output_path}")

    @abstractmethod
    def create_camera_device(self) -> azure_kinect.Device | FakeCamera:
        raise NotImplementedError

    @abstractmethod
    def create_audio_devices(self):
        raise NotImplementedError
