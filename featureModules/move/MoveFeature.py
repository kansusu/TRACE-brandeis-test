import torch
import torch.nn.functional as F
from featureModules.move.move_classifier import (
    rec_common_ground,
    hyperparam,
    modalities,
)
from featureModules.move.closure_rules import CommonGround
from transformers import BertTokenizer, BertModel
import cv2
import opensmile

from logger import Logger

# length of the sequence (the utterance of interest + 3 previous utterances for context)
UTTERANCE_HISTORY_LEN = 4

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("move classifier device", device)


class MoveFeature:
    def __init__(self, txt_log_file=None):
        self.model = torch.load(r"featureModules\move\production_move_classifier.pt").to(device)
        self.model.eval()

        self.tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
        self.bert_model: BertModel = BertModel.from_pretrained("bert-base-uncased").to(
            device
        )  # pyright: ignore

        self.smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )

        self.bert_embedding_history = torch.zeros(
            (UTTERANCE_HISTORY_LEN, 768), device=device
        )
        self.opensmile_embedding_history = torch.zeros(
            (UTTERANCE_HISTORY_LEN, 88), device=device
        )

        self.closure_rules = CommonGround()
        self.class_names = ["STATEMENT", "ACCEPT", "DOUBT"]

        self.most_recent_prop = "no prop"

        self.logger = Logger(file=txt_log_file, stdout=True)
        self.logger.clear()


    def update_bert_embeddings(self, name, text):
        input_ids = torch.tensor(self.tokenizer.encode(text), device=device).unsqueeze(0)
        cls_embeddings = self.bert_model(input_ids)[0][:, 0]

        self.bert_embedding_history = torch.cat([self.bert_embedding_history[1:], cls_embeddings])

    def update_smile_embeddings(self, name, audio_file):
        embedding = torch.tensor(self.smile.process_file(audio_file).to_numpy(), device=device)

        self.opensmile_embedding_history = torch.cat([self.opensmile_embedding_history[1:], embedding])

    def renderBanks(self, frame, xSpace, yCord, bankLabel):
        colors = [(0, 0, 255), (255, 0, 0), (0, 255, 0), (128, 0, 128), (0, 215, 255)]
        blocks = len(colors) + 1
        blockWidth = 50
        blockHeight = 50
        h,w,_ = frame.shape
        start = w - (xSpace * blocks)
        p2 = h - yCord
        (tw, th), _ = cv2.getTextSize(bankLabel, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
        labelCoords = (int(start) - int(tw / 2), (int(blockHeight / 2) + int(th / 2)) + p2)
        cv2.putText(frame, bankLabel, labelCoords, cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)

        for i in range(1, blocks):
            p1 = start + (xSpace * i)
            cv2.rectangle(frame, 
                (p1, p2), 
                (p1 + blockWidth, p2 + blockHeight), 
                color=colors[i - 1],
                thickness=3)
            
            (tw, th), _ = cv2.getTextSize("1", cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
            centerCoordinates = ((int(blockWidth / 2) - int(tw / 2)) + p1, (int(blockHeight / 2) + int(th / 2)) + p2)
            cv2.putText(frame, "1", centerCoordinates, cv2.FONT_HERSHEY_SIMPLEX, 1, colors[i - 1], 2)

    def processFrame(self, utterances_and_props, frame, frameIndex):
        for name, text, prop, audio_file in utterances_and_props:
            if prop != "no prop":
                self.most_recent_prop = prop

            self.update_bert_embeddings(name, text)
            in_bert = self.bert_embedding_history

            self.update_smile_embeddings(name, audio_file)
            in_open = self.opensmile_embedding_history

            # TODO: other inputs for move classifier
            in_cps = torch.zeros((UTTERANCE_HISTORY_LEN, 3), device=device)
            in_action = torch.zeros((UTTERANCE_HISTORY_LEN, 78), device=device)
            in_gamr = torch.zeros((UTTERANCE_HISTORY_LEN, 243), device=device)

            # out = F.softmax(self.model(in_bert, in_open, in_cps, in_action, in_gamr, hyperparam, modalities))
            out = torch.sigmoid(self.model(in_bert, in_open, in_cps, in_action, in_gamr, hyperparam, modalities))
            out = out.cpu().detach().numpy()

            present_class_indices = (out > 0.5)
            move = [self.class_names[idx] for idx, class_present in enumerate(present_class_indices) if class_present]

            self.closure_rules.update(move, self.most_recent_prop)
            update = ""
            update += "FRAME: " + str(frameIndex) + "\n"
            update += "Q bank\n"
            update += str(self.closure_rules.qbank) + "\n"
            update += "E bank\n"
            update += str(self.closure_rules.ebank) + "\n"
            update += "F bank\n"
            update += str(self.closure_rules.fbank) + "\n"
            if prop == "no prop":
                update += f"{name}: {text} ({self.most_recent_prop}), {out}\n\n"
            else:
                update += f"{name}: {text} => {self.most_recent_prop}, {out}\n\n"

            self.logger.append(update)

        self.renderBanks(frame, 75, 25, "F BANK:")
        self.renderBanks(frame, 75, 100, "E BANK:")
        cv2.putText(frame, "Move classifier is live", (50, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
