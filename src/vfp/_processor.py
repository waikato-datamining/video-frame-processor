import cv2
import os
from typing import Callable, List
from datetime import datetime


def decode_fourcc(cc):
    """
    Turns the float into a four letter codec string.
    Taken from here:
    https://stackoverflow.com/a/49138893/4698227
    :param cc: the codec as float
    :type cc: float
    :return: the codec string
    :rtype: str
    """
    return "".join([chr((int(cc) >> 8 * i) & 0xFF) for i in range(4)])


def dummy_frame_processing(processor, frame, frame_no, pos_msec):
    """
    Dummy frame processing method. Just outputs the frame number to stdout.

    :param processor: the processor object triggering the processing
    :type processor: Processor
    :param frame: the frame
    :type frame: numpy.ndarray
    :param frame_no: the frame number
    :type frame_no: int
    :param pos_msec: the current position in milli-seconds
    :type pos_msec: float
    """
    ts = datetime.utcfromtimestamp(pos_msec / 1000.0).time().isoformat(timespec='milliseconds')
    print("Processing: frame#=%d, timestamp=%s" % (frame_no, ts))


def dummy_processing_finished(processor, video_capture_opened):
    """
    Dummy processing finished method. Just outputs that processing has finished.

    :param processor: the processor object triggering the call
    :type processor: Processor
    :param video_capture_opened: whether processing was successful (ie video capture was opened)
    :type video_capture_opened: bool
    """
    print("Processing finished (capture opened: %s)" % str(video_capture_opened))


LOGGING_TYPE_INFO = 1
LOGGING_TYPE_DEBUG = 2
LOGGING_TYPE_ERROR = 3


def simple_logging(type, *args):
    """
    Just uses the print method to output the arguments.

    :param type: the message type
    :type type: int
    :param args: the arguments to output
    """
    print(*args)


class Parameters(object):
    """
    Dummy class that we abuse for storing custom parameters for the process_frame method.
    """
    pass


class Processor(object):
    """"
    Simple poller class that polls an input directory for files for processing and moves them (or deletes them)
    to the output directory. The temporary directory can be used for generating output files before moving them
    to the output directory itself (in case other processes are polling the output directory).
    """

    def __init__(self, process_frame=None, processing_finished=None, nth_frame=1, max_frames=-1, logging=simple_logging,
                 params=Parameters(), verbose=False, output_timestamp=False):
        """
        Initializes the processor.

        :param process_frame: the method to call for processing a frame
        :type process_frame: object
        :param processing_finished: the method to call when the processing has finished, eg for clean ups
        :type processing_finished: object
        :param nth_frame: how many frames to skip, 1 processes every frame, 2 skips every 2nd frame
        :type nth_frame: int
        :param max_frames: the maximum number of frames to process, use <1 for no unlimited
        :type max_frames: int
        :param logging: the method to use for logging
        :type logging: object
        :param params: the object for encapsulating additional parameters for the check_file/process_file methods
        :type params: Parameters
        :param verbose: Whether to be more verbose with the logging output.
        :type verbose: bool
        :param output_timestamp: whether to print a timestamp in the log messages
        :type output_timestamp: bool
        """

        self._webcam_id = None
        self._video_file = None
        self.nth_frame = nth_frame
        self.max_frames = max_frames
        self.process_frame = process_frame
        self.processing_finished = processing_finished
        self.logging = logging
        self.is_listing_files = False
        self.is_processing_frames = False
        self.params = params
        self.verbose = verbose
        self.output_timestamp = output_timestamp
        self._stopped = False

    @property
    def logging(self):
        """
        Returns the logging method.

        :return: the method in use
        :rtype: function
        """
        return self._logging

    @logging.setter
    def logging(self, fn):
        """
        Sets the logging function.

        :param fn: the method to use
        :type fn: function
        """
        self._logging = fn

    @property
    def process_frame(self):
        """
        Returns the process frame method.

        :return: the method in use
        :rtype: function
        """
        return self._process_frame

    @process_frame.setter
    def process_frame(self, fn: Callable[[str, str, "Poller"], List[str]]):
        """
        Sets the process frame function.

        :param fn: the method to use
        :type fn: function
        """
        self._process_frame = fn

    @property
    def processing_finished(self):
        """
        Returns the processing finished method.

        :return: the method in use
        :rtype: function
        """
        return self._processing_finished

    @processing_finished.setter
    def processing_finished(self, fn: Callable[[str, str, "Poller"], List[str]]):
        """
        Sets the processing finished function.

        :param fn: the method to use
        :type fn: function
        """
        self._processing_finished = fn

    def debug(self, *args):
        """
        Outputs the arguments via 'log' if verbose is enabled.

        :param args: the debug arguments to output
        """
        if self.verbose:
            self._log(LOGGING_TYPE_DEBUG, *args)

    def info(self, *args):
        """
        Outputs the arguments via 'log' if progress is enabled.

        :param args: the info arguments to output
        """
        self._log(LOGGING_TYPE_INFO, *args)

    def error(self, *args):
        """
        Outputs the arguments via 'log'.

        :param args: the error arguments to output
        """
        self._log(LOGGING_TYPE_ERROR, *args)

    def _log(self, type, *args):
        """
        Outputs the arguments via the logging function.

        :param args: the arguments to output
        """
        if self._logging is not None:
            if self.output_timestamp:
                self._logging(type, *("%s - " % str(datetime.now()), *args))
            else:
                self._logging(type, *args)

    def keyboard_interrupt(self):
        """
        Prints an error message and stops the polling.
        """
        self.error("Interrupted, exiting")
        self.stop()

    def stop(self):
        """
        Stops the polling. Can be used by the check/processing methods in case of a fatal error.
        """
        self._stopped = True
        self.is_processing_frames = False

    @property
    def is_stopped(self):
        """
        Returns whether the polling got stopped, e.g., interrupted by the user.

        :return: whether it was stopped
        :rtype: bool
        """
        return self._stopped

    @property
    def is_busy(self):
        """
        Returns whether the processor is busy.

        :return: True if processing frames
        :rtype: bool
        """
        return self.is_processing_frames

    def _check(self):
        """
        For performing checks before starting the polling.
        Raises an exception if any check should fail.
        """

        if (self._webcam_id is None) and (self._video_file is None):
            raise Exception("Neither webcam ID nor video file supplied!")
        if self._video_file is not None:
            if not os.path.exists(self._video_file):
                raise Exception("Video file does not exist: %s" % self._video_file)
            if os.path.isdir(self._video_file):
                raise Exception("Video file points to directory: %s" % self._video_file)
        if self.process_frame is None:
            raise Exception("No method for processing frames supplied!")
        
    def _retrieve_info(self, video_capture):
        """
        Returns a dictionary with information about the opened device.
        
        :param video_capture: the capture device to query
        :type video_capture: cv2.VideoCapture
        :return: the device information
        :rtype: dict
        """
        result = dict()

        result["fps"] = video_capture.get(cv2.CAP_PROP_FPS)
        result["width"] = video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        result["height"] = video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        result["codec"] = decode_fourcc(video_capture.get(cv2.CAP_PROP_FOURCC))

        if self._webcam_id is not None:
            result["brightness"] = video_capture.get(cv2.CAP_PROP_CONTRAST)
            result["contrast"] = video_capture.get(cv2.CAP_PROP_CONTRAST)
            result["saturation"] = video_capture.get(cv2.CAP_PROP_SATURATION)
            result["hue"] = video_capture.get(cv2.CAP_PROP_HUE)
            result["gain"] = video_capture.get(cv2.CAP_PROP_GAIN)
            result["exposure"] = video_capture.get(cv2.CAP_PROP_EXPOSURE)
            result["whitebalance"] = video_capture.get(cv2.CAP_PROP_WB_TEMPERATURE)
            result["gamma"] = video_capture.get(cv2.CAP_PROP_GAMMA)
            result["temperature"] = video_capture.get(cv2.CAP_PROP_TEMPERATURE)
            result["zoom"] = video_capture.get(cv2.CAP_PROP_ZOOM)
            result["focus"] = video_capture.get(cv2.CAP_PROP_FOCUS)
            result["iso_speed"] = video_capture.get(cv2.CAP_PROP_ISO_SPEED)
            result["backlight"] = video_capture.get(cv2.CAP_PROP_BACKLIGHT)
            result["pan"] = video_capture.get(cv2.CAP_PROP_PAN)
            result["tilt"] = video_capture.get(cv2.CAP_PROP_TILT)
            result["roll"] = video_capture.get(cv2.CAP_PROP_ROLL)
            result["iris"] = video_capture.get(cv2.CAP_PROP_IRIS)
            result["auto_focus"] = video_capture.get(cv2.CAP_PROP_AUTOFOCUS)
            result["auto_exposure"] = video_capture.get(cv2.CAP_PROP_AUTO_EXPOSURE)
            result["sharpness"] = video_capture.get(cv2.CAP_PROP_SHARPNESS)
            result["monochrome"] = video_capture.get(cv2.CAP_PROP_MONOCHROME)
            result["sample_aspect_ratio_num"] = video_capture.get(cv2.CAP_PROP_SAR_NUM)
            result["sample_aspect_ratio_den"] = video_capture.get(cv2.CAP_PROP_SAR_DEN)
            result["auto_white_balance"] = video_capture.get(cv2.CAP_PROP_AUTO_WB)
            result["white_balance_temperature"] = video_capture.get(cv2.CAP_PROP_WB_TEMPERATURE)
        else:
            result["frame_count"] = video_capture.get(cv2.CAP_PROP_FRAME_COUNT)
            result["bitrate"] = video_capture.get(cv2.CAP_PROP_BITRATE)
            result["pixel_format"] = decode_fourcc(video_capture.get(cv2.CAP_PROP_CODEC_PIXEL_FORMAT))

        return result
        
    def process(self, webcam_id=None, video_file=None):
        """
        Performs the processing.

        :param webcam_id: the ID of the webcam to retrieve frames from
        :type webcam_id: int
        :param video_file: the video file to process
        :type video_file: str
        """

        self._stopped = False
        self._webcam_id = webcam_id
        self._video_file = video_file
        self._check()

        if self._video_file is not None:
            self.info("Opening file: %s" % self._video_file)
            video_capture = cv2.VideoCapture(self._video_file)
        else:
            self.info("Opening webcam: %d" % self._webcam_id)
            video_capture = cv2.VideoCapture(self._webcam_id)
        self.params.video_capture = video_capture

        frame_no = 0
        if not video_capture.isOpened():
            video_capture_opened = False
            self.error("Failed to open video capture!")
        else:
            video_capture_opened = True
            self.params.info = self._retrieve_info(video_capture)
            if self.verbose:
                self.info("Info:", self.params.info)

            while video_capture.isOpened() and not self.is_stopped:
                ret, frame = video_capture.read()
                if not ret:
                    break
                frame_no += 1
                if (frame_no % self.nth_frame) == 0:
                    self.is_processing_frames = True
                    self.process_frame(self, frame, frame_no, video_capture.get(cv2.CAP_PROP_POS_MSEC))
                    self.is_processing_frames = False

                if (self.max_frames > 0) and (frame_no >= self.max_frames):
                    self.info("Reached maximum number of frames: %d" % self.max_frames)
                    break

        video_capture.release()

        if self.processing_finished is not None:
            self.processing_finished(self, video_capture_opened)

    def query(self, webcam_id=None, video_file=None):
        """
        Returns information on the webcam or video file.

        :param webcam_id: the ID of the webcam to query
        :type webcam_id: int
        :param video_file: the video file to query
        :type video_file: str
        :return: the dictionary with device/file information
        :rtype: dict
        """

        self._stopped = False
        self._webcam_id = webcam_id
        self._video_file = video_file
        self._check()

        if self._video_file is not None:
            self.info("Opening file: %s" % self._video_file)
            video_capture = cv2.VideoCapture(self._video_file)
        else:
            self.info("Opening webcam: %d" % self._webcam_id)
            video_capture = cv2.VideoCapture(self._webcam_id)
        self.params.video_capture = video_capture

        if not video_capture.isOpened():
            result = None
            self.error("Failed to open video capture!")
        else:
            result = self._retrieve_info(video_capture)

        video_capture.release()

        return result