# video-frame-processor
Python 3 library to make video frame processing easier.

It allows processing video from webcams or video files, 
with the user only having to supply a method that processes
the actual video frames. Everything else is handled by the
library.

## Installation

Install via pip:

```
pip install video-frame-processor
```

## Usage

The `vfp.Processor` class is used for processing frames from a webcam or from a video file.
Under the hood it uses opencv for obtaining the frames (type: `numpy.ndarray`).

There are two main methods available from the `Processor` class:
* `process` - for processing frames from a video
* `query` - for obtaining information about a video (e.g., width, height, fps, codec)

Both methods take either the webcam ID (integer, typically 0 if there is a webcam available) 
or the path to the video file to process.

The actual processing of a frame happens with a user-supplied method, which takes the following
arguments:
* `processor` - the `Processor` instance that called this method
* `frame` - the frame image (`numpy.ndarray`)
* `frame_no` - the frame number (`int`)
* `pos_msec` - the position in milli-seconds (`float`)

The following configures the processor to process every 10th frame, a maximum of 2000 frames
to be read from the video source altogether and to be verbose with the output:

```python
from vfp import Processor

p = Processor(nth_frame=10, max_frames=2000, verbose=True)
```

The `params` variable of a `Processor` instance allows storing of additional parameters
(e.g., the `cv2.VideoCapture` instance is available as `video_capture` and the video information
is available as `info`). 

The following examples shows a processing method that simply stores the images using the timestamp 
as file name in the `/tmp` directory. The output directory is made accessible via the `output_dir` 
value of the `params` variable. It uses the first webcam as video source:

```python
from vfp import Processor
from datetime import datetime
import cv2

def save_frames(processor, frame, frame_no, pos_msec):
    ts = datetime.utcfromtimestamp(pos_msec / 1000.0).time().strftime("%H%M%S.%f")
    cv2.imwrite(processor.params.output_dir + "/" + ts + ".jpg", frame)

p = Processor(nth_frame=10, max_frames=2000, process_frame=save_frames, verbose=True)
p.params.output_dir = "/tmp"   # used by the "save_frames" method 
p.process(webcam_id=0)
```

For processing the video `/some/where/video.mp4`, the call would look like:

```python
p.process(video_file="/some/where/video.mp4")
```

For custom clean-up operations, once the video has been processed, you can supply
a method with the following signature:

* `processor` - the `Processor` instance that called this method
* `video_capture_opened` - whether the opening of the video source was successful (`bool`)


## Custom logging

By supplying a method to the `logging` property, you can customize the logging
that occurs via the `info`, `debug` and `error` method calls of the Processor. 
The example below uses the Python logging framework.  

```python
from vfp import Processor, LOGGING_TYPE_DEBUG, LOGGING_TYPE_ERROR
import logging

_logger = None
def custom_logging(*args):
    global _logger
    if _logger is None:
        logging.basicConfig()
        _logger = logging.getLogger("vfp")
        _logger.setLevel(logging.DEBUG)
    str_args = [str(x) for x in args]
    if type == LOGGING_TYPE_ERROR:
        _logger.error(" ".join(str_args))
    elif type == LOGGING_TYPE_DEBUG:
        _logger.debug(" ".join(str_args))
    else:
        _logger.info(" ".join(str_args))

p = Processor()
# ... setting more options
p.logging = custom_logging
p.output_timestamp = False # the Python logging framework should handle that instead
p.process(webcam_id=0)
```
