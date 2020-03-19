from imutils.object_detection import non_max_suppression
import pytesseract
import numpy as np
import cv2
import pandas as pd
import glob
import operator

class Reader:
    def __init__(self, image):
        self.__image=cv2.imread(image)
        self.__kernel= np.ones((5, 5), np.uint8)

    def __decode_predictions(self, scores, geometry, minconfidence):
        (numRows, numCols) = scores.shape[2:4]
        rects = []
        confidences = []

        for y in range(0, numRows):
            scoresData = scores[0, 0, y]
            xData0 = geometry[0, 0, y]
            xData1 = geometry[0, 1, y]
            xData2 = geometry[0, 2, y]
            xData3 = geometry[0, 3, y]
            anglesData = geometry[0, 4, y]

            for x in range(0, numCols):
                if scoresData[x] < minconfidence:
                    continue

                (offsetX, offsetY) = (x * 4.0, y * 4.0)

                angle = anglesData[x]
                cos = np.cos(angle)
                sin = np.sin(angle)

                h = xData0[x] + xData2[x]
                w = xData1[x] + xData3[x]

                endX = int(offsetX + (cos * xData1[x]) + (sin * xData2[x]))
                endY = int(offsetY - (sin * xData1[x]) + (cos * xData2[x]))
                startX = int(endX - w)
                startY = int(endY - h)

                rects.append((startX, startY, endX, endY))
                confidences.append(scoresData[x])

        return (rects, confidences)

    def locate_number(self):
        image=self.__get_image_treatment()
        image = cv2.erode(image, self.__kernel, iterations=1)
        image = cv2.dilate(image, self.__kernel, iterations=1)

        minconfidence = 0.5
        # The EAST text requires that your input image dimensions be multiples of 32, so if you choose to adjust your --width and --height values, make sure they are multiples of 32!
        height=320
        width=320
        padding=0.0
        east="frozen_east_text_detection.pb"
        (origH, origW) = image.shape[:2]

        (newW, newH) = (width, height)
        rW = origW / float(newW)
        rH = origH / float(newH)

        image_r = cv2.resize(image, (newW, newH))
        (H, W) = image_r.shape[:2]

        layerNames = [
            "feature_fusion/Conv_7/Sigmoid",
            "feature_fusion/concat_3"]

        # print("[INFO] loading EAST text detector...")
        net = cv2.dnn.readNet(east)



        blob = cv2.dnn.blobFromImage(image_r, 1.0, (W, H), (123.68, 116.78, 103.94), swapRB=True, crop=False)
        net.setInput(blob)
        (scores, geometry) = net.forward(layerNames)

        (rects, confidences) = self.__decode_predictions(scores, geometry, minconfidence)
        boxes = non_max_suppression(np.array(rects), probs=confidences)

        best_bb_start=(0,0)
        best_bb_end=(0,0)
        for (startX, startY, endX, endY) in boxes:
            startX = int(startX * rW)
            startY = int(startY * rH)
            endX = int(endX * rW)
            endY = int(endY * rH)

            dX = int((endX - startX) * padding)
            dY = int((endY - startY) * padding)

            startX = max(0, startX - dX)
            startY = max(0, startY - dY)
            endX = min(origW, endX + (dX * 2))
            endY = min(origH, endY + (dY * 2))

            cv2.rectangle(image, (startX, startY), (endX, endY), (0, 0, 255), 2)


            if endY>best_bb_end[1]:
                best_bb_start=(startX,startY)
                best_bb_end = (endX, endY)


        cv2.imshow("Best bb", image)
        cv2.waitKey(0)



        return best_bb_start, best_bb_end

    def __get_image_treatment(self):
        hsv = cv2.cvtColor(self.__image, cv2.COLOR_BGR2HSV)
        lower_val = np.array([0, 0, 0])
        upper_val = np.array([179, 255, 80])
        mask = cv2.inRange(hsv, lower_val, upper_val)
        masked = cv2.bitwise_not(mask)
        return cv2.cvtColor(masked,cv2.COLOR_GRAY2RGB)


    def identify_number(self, bb_start, bb_end):
        image=self.__get_image_treatment()
        #image = cv2.dilate(image, self.__kernel, iterations=1)

        (startX, startY)=bb_start
        (endX, endY)=bb_end
        text=""
        if startX != startY:

            # Need to especify the path only in widows systems
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

            roi = image[startY:endY, startX:endX]
            config = ("-l eng --oem 1 --psm 7 -c tessedit_char_whitelist=0123456789")
            text = pytesseract.image_to_string(roi, config=config)


            #print(startX, startY, endX, endY)
            #print("{}\n".format(text))
            """
            text = "".join([c if ord(c) < 128 else "" for c in text]).strip()
            cv2.rectangle(image, (startX, startY), (endX, endY), (0, 0, 255), 2)
            cv2.putText(image, text, (startX, startY - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        
            cv2.imshow("Text Detection", image)
            cv2.waitKey(0)
            """
        return text

    def separation(self, bb_start, bb_end):
        image=self.__get_image_treatment()
        image = cv2.dilate(image, self.__kernel, iterations=1)
        image = cv2.erode(image, self.__kernel, iterations=1)
        image = image[bb_start[1]:bb_end[1],bb_start[0]:bb_end[0]]
        image_grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # step1
        edges = cv2.adaptiveThreshold(image_grey, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 3, -2)
        #cv2.imshow("edges", edges)
        #cv2.waitKey(0)

        # step2
        kernel = np.ones((1, 2), dtype="uint8")
        dilated = cv2.dilate(edges, kernel)

        im2, ctrs, hier = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        #print(len(ctrs))


        # sort contours
        sorted_ctrs = sorted(ctrs, key=lambda ctr: cv2.boundingRect(ctr)[0])

        #maxsize_rois=4
        all_rois=[]
        rois=[]
        for i, ctr in enumerate(sorted_ctrs):
            # Get bounding box
            x, y, w, h = cv2.boundingRect(ctr)
            roi = image[y:y + h, x:x + w]
            all_rois.append([roi, w+h])
            """
            print(x, y, w, h)
            cv2.imshow("roii", roi)
            cv2.waitKey(0)
            """
            if w+h>120 and w>45 and h>90:
                rois.append(roi)
                print(x, y, w, h)
                cv2.imshow("roii", roi)
                cv2.waitKey(0)
        return rois

        """
        best_rois=[]
        rois=[]
        if len(all_rois)>maxsize_rois:
            for j in range(maxsize_rois):
                pos=0
                best_roi=(0,0)
                for i in range(len(all_rois)):
                    if all_rois[i][1]>best_roi[1]:
                        best_roi=all_rois[i]
                        pos=i
                best_rois.append((pos,best_roi))
                all_rois.pop(pos)
            best_rois=sorted(best_rois,key=lambda x:x[0])

            for r in best_rois:
                rois.append(r[1][0])
        else:
            for r in all_rois:
                rois.append(r[0])
        return rois
        """

    def identify_number_2(self, bb_start, bb_end):
        text = ""
        if bb_start!=bb_end:
            images=self.separation(bb_start,bb_end)
            print(len(images))

            # Need to especify the path only in widows systems
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            config = ("-l eng --oem 1 --psm 10 -c tessedit_char_whitelist=0123456789")
            for image in images:
                text =text+ pytesseract.image_to_string(image, config=config)

                # print(startX, startY, endX, endY)
                # print("{}\n".format(text))
                """
                text = "".join([c if ord(c) < 128 else "" for c in text]).strip()
                cv2.rectangle(image, (bb_start[0], bb_start[1]), (bb_end[0], bb_end[1]), (0, 0, 255), 2)
                cv2.putText(image, text, (bb_start[0], bb_start[1] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
    
                cv2.imshow("Text Detection", image)
                cv2.waitKey(0)
                """
        return text






#Usage Example

GT=pd.read_csv("images/GroundTruth.csv", sep=";")
files=glob.glob("images/TestSamples/*.TIF")
trues=0

for i in range(0,len(files)):
    r= Reader(files[i])
    bb_start, bb_end=r.locate_number()
    sol=r.identify_number_2(bb_start,bb_end)

    gt = GT.at[i, "Real"]

    try:
        if int(sol)==gt:
            trues=trues+1
    except:
        pass
    print(i, gt, sol)


print("Trues: ",trues,"/",len(files))
print("%True: ",trues/len(files))





"""
i = Reader("images/TestSamples/0005.TIF")
bb_start, bb_end=i.locate_number()
print(i.identify_number_2(bb_start,bb_end))


"""

"""
#print(i.identify_number(bb_start,bb_end))

files=glob.glob("images/TestSamples/*.TIF")
trues=0

for i in range(0,len(files)):
    print(files[i])
    r= Reader(files[i])
    bb_start, bb_end=r.locate_number()
    sol=r.identify_number_2(bb_start,bb_end)
    print(sol)
"""
