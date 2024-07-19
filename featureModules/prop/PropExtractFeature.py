from dataclasses import dataclass
from featureModules.IFeature import *
from featureModules.asr.AsrFeature import UtteranceInfo
from logger import Logger
from utils import *
from featureModules.prop.demo import process_sentence, load_model

@dataclass
class PropInfo:
    utterance_id: int
    prop: str

class PropExtractFeature(IFeature):
    LOG_FILE = "propOutput.csv"

    def __init__(self, log_dir=None):
        model_dir = r'featureModules\prop\data\prop_extraction_model'
        self.model, self.tokenizer = load_model(model_dir)

        if log_dir is not None:
            self.logger = Logger(file=log_dir / self.LOG_FILE)
        else:
            self.logger = Logger()

        self.logger.write_csv_headers("frame", "utterance_id", "proposition", "utterance_text")

        # map utterance ids to propositions
        self.prop_lookup = {}

    def processFrame(self, frame, new_utterance_ids: list[int], utterance_lookup: list[UtteranceInfo] | dict[int, UtteranceInfo], frame_count: int):
        for i in new_utterance_ids:
            utterance_info = utterance_lookup[i]
            colors = ["red", "blue", "green", "purple", "yellow"]
            numbers = ["10", "20", "30", "40", "50"]
            if not any(i in utterance_info.text for i in colors + numbers):
                prop = "no prop"
            else:
                prop = process_sentence(utterance_info.text, self.model, self.tokenizer, verbose=False)

            self.prop_lookup[i] = PropInfo(i, prop)
            self.logger.append_csv(frame_count, i, prop, utterance_info.text)

        cv2.putText(frame, "Prop extract is live", (50,400), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2, cv2.LINE_AA)
