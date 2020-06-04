# Video Annotation
Roberto Negro #211505\
Fundamentals of Video and Image Processing\
Università degli Studi di Trento a.a. 2019/20

# Dependencies
* Python 3.6
* pip install numpy==1.18.4 Pygments==2.6.1 coloredlogs==14.0 PySide2==5.14.2.1 opencv-python-headless==4.2.0.34 qimage2ndarray==1.8.3 fbs==0.8.6 pyinstaller==3.4
* pip install --upgrade "setuptools<45.0.0"

If you want to bundle this software in Windows, you need to copy OpenCV dll from C:/Users/<YOUR_USER>/anaconda3/envs/<YOUR_ENV>/cv2/opencv_videoio_ffmpeg420_64.dll to src/freeze/windows/opencv_videoio_ffmpeg420_64.dll


Tested on Mac OS High Sierra (10.13.6), Mac OS Mojave (10.15.4) and Windows 10, with .mp4 and .avi files.

# Executing and compiling
_Execute_: fbs run\
_Compile_: fbs freeze or fbs release

# Troubleshooting
If "Can not find path ./libshiboken2.abi3.5.14.dylib" error on fbs freeze:\
given <SITE_PACKAGES> as "~/.conda/envs/<YOUR_ENV>/lib/python3.6/site-packages" path, copy <SITE_PACKAGES>/shiboken2/libshiboken2.abi3.5.14.dylib file both to <SITE_PACKAGES>/PyInstaller/hooks/ and <SITE_PACKAGES>/PySide2/ folders.

For bundling on Windows, you will need NSIS (with its installation directory set in PATH environment variable) and pywin32 (pip install pywin32) installed.