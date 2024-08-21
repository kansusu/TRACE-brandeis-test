from typing import final
import cv2 as cv

from mmdemo.base_feature import BaseFeature
from mmdemo.base_interface import BaseInterface
from mmdemo.interfaces import (  # FrameCountInterface,; GazeInterface,
    CameraCalibrationInterface,
    ColorImageInterface,
    CommonGroundInterface,
    GazeConesInterface,
    GestureConesInterface,
    SelectedObjectsInterface
)
from mmdemo.utils.coordinates import _convert2D
import re

# import helpers
# from mmdemo.features.proposition.helpers import ...

#TODO add documentation 

class Color():
    def __init__(self, name, color):
        self.name = name
        self.color = color

colors = [
        Color("red", (0, 0, 255)), 
        Color("blue", (255, 0, 0)), 
        Color("green", (19, 129, 51)), 
        Color("purple", (128, 0, 128)), 
        Color("yellow", (0, 215, 255))]

fontScales = [1.5, 1.5, 0.75, 0.5, 0.5]
fontThickness = [3, 3, 2, 2, 2]


@final
class OutputFrames(BaseFeature[ColorImageInterface]):
    @classmethod
    def get_input_interfaces(cls):
        return [
            ColorImageInterface,
            GazeConesInterface,
            GestureConesInterface,
            SelectedObjectsInterface,
            CommonGroundInterface
        ]

    @classmethod
    def get_output_interface(cls):
        return ColorImageInterface

    def initialize(self):
        # initialize prop model
        pass

    def get_output(
        self,
        color: ColorImageInterface,
        gaze: GazeConesInterface,
        gesture: GestureConesInterface,
        objects: SelectedObjectsInterface,
        common: CommonGroundInterface,
        calibration: CameraCalibrationInterface
    ):
        if not color.is_new() or not gaze.is_new() or not gesture.is_new() or not objects.is_new() or not common.is_new() or not calibration.is_new():
            return None
        
        #render gaze vectors
        for cone in gaze.cones:
            self.projectVectorLines(cone, color.frame, calibration, False, False, True)

        #render gesture vectors
        for cone in gesture.cones:
            self.projectVectorLines(cone, color.frame, calibration, True, False, False)

        #render objects
        for obj in objects.objects:
            color = (0,255,0) if obj[1] == True else (0,0,255)
            block = obj[0]
            cv.rectangle(color.frame, 
                    (int(block.p1[0]), int(block.p1[1])),
                    (int(block.p2[0]), int(block.p2[1])),
                    color=color,
                    thickness=5)

        #render common ground
        self.renderBanks(color.frame, 130, 260, "FBank", common.fbank)
        self.renderBanks(color.frame, 130, 130, "EBank",  common.ebank)

        return color

    def projectVectorLines(self, cone, frame, calibration, includeY, includeZ, gaze):
        baseUpY, baseDownY, baseUpZ, baseDownZ = cone.conePointsBase()
        vertexUpY, vertexDownY, vertexUpZ, vertexDownZ = cone.conePointsVertex()

        if(gaze):
            yColor = (255, 107, 170)
            ZColor = (107, 255, 138)
        else:
            yColor = (255, 255, 0)
            ZColor = (243, 82, 121)

        if includeY:
            baseUp2DY = _convert2D(baseUpY, calibration.cameraMatrix, calibration.distortion)       
            baseDown2DY = _convert2D(baseDownY, calibration.cameraMatrix, calibration.distortion)    
            vertexUp2DY = _convert2D(vertexUpY, calibration.cameraMatrix, calibration.distortion)  
            vertexDown2DY = _convert2D(vertexDownY, calibration.cameraMatrix, calibration.distortion)
            
            pointUpY = (int(baseUp2DY[0]),int(baseUp2DY[1]))
            pointDownY = (int(baseDown2DY[0]),int(baseDown2DY[1]))

            vertexPointUpY = (int(vertexUp2DY[0]),int(vertexUp2DY[1]))
            vertexPointDownY = (int(vertexDown2DY[0]),int(vertexDown2DY[1]))
            
            cv.line(frame, vertexPointUpY, pointUpY, color=yColor, thickness=5)
            cv.line(frame, vertexPointDownY, pointDownY, color=yColor, thickness=5)

        if includeZ:
            vertexUp2DZ = _convert2D(vertexUpZ, calibration.cameraMatrix, calibration.distortion)
            vertexDown2DZ = _convert2D(vertexDownZ, calibration.cameraMatrix, calibration.distortion)
            baseUp2DZ = _convert2D(baseUpZ, calibration.cameraMatrix, calibration.distortion)      
            baseDown2DZ = _convert2D(baseDownZ, calibration.cameraMatrix, calibration.distortion)

            pointUpZ = (int(baseUp2DZ[0]),int(baseUp2DZ[1]))
            pointDownZ = (int(baseDown2DZ[0]),int(baseDown2DZ[1]))

            vertexPointUpZ = (int(vertexUp2DZ[0]),int(vertexUp2DZ[1]))
            vertexPpointDownZ = (int(vertexDown2DZ[0]),int(vertexDown2DZ[1]))

            cv.line(frame, vertexPointUpZ, pointUpZ, color=ZColor, thickness=5)
            cv.line(frame, vertexPpointDownZ, pointDownZ, color=ZColor, thickness=5)

    def getPropValues(self, propStrings, match):
        label = []
        for prop in propStrings:
            prop_match = re.match(r'(' + match + r')\s*(=|<|>|!=)\s*(.*)', prop)
            if prop_match:
                block = prop_match[1]
                relation = prop_match[2]
                rhs = prop_match[3]
                if(relation == '<' or relation == '>' or relation == '!='):
                    label.append(relation + rhs)
                else:
                    label.append(rhs)
        return label
    
    def renderBanks(self, frame, xSpace, yCord, bankLabel, bankValues):
        blocks = len(colors) + 1
        blockWidth = 112
        blockHeight = 112

        h,w,_ = frame.shape
        start = w - (xSpace * blocks)
        p2 = h - yCord
        (tw, th), _ = cv.getTextSize(bankLabel, cv.FONT_HERSHEY_SIMPLEX, 1.5, 3)
        labelCoords = (int(start) - int(tw / 4), (int(blockHeight / 2) + int(th / 2)) + p2)
        cv.putText(frame, bankLabel, labelCoords, cv.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 3)

        for i in range(1, blocks):
            p1 = start + (xSpace * i)
            color = colors[i - 1]
            cv.rectangle(frame, 
                (p1, p2), 
                (p1 + blockWidth, p2 + blockHeight), 
                color=color.color,
                thickness=-1)
            
            labels = self.getPropValues(bankValues, color.name)
            numberLabels = min(len(labels), 5)
            if(numberLabels > 0):
                for i, line in enumerate(labels):
                    (tw, th), _ = cv.getTextSize(line, cv.FONT_HERSHEY_SIMPLEX, fontScales[numberLabels - 1], fontThickness[numberLabels -1])
                    y = ((int(blockHeight / (numberLabels + 1)) + int(th / 3)) * (i + 1)) + p2
                    x = (int(blockWidth / 2) - int(tw / 2)) + p1
                    cv.putText(frame, line, (x, y), cv.FONT_HERSHEY_SIMPLEX, fontScales[numberLabels - 1], (0,0,0), fontThickness[numberLabels -1])

