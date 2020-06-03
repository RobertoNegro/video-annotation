# Video Annotation
Roberto Negro #211505\
Fundamentals of Video and Image Processing\
Università degli Studi di Trento a.a. 2019/20

# Dependencies
* Python 3.6
* pip install numpy Pygments coloredlogs PySide2 opencv-python-headless qimage2ndarray fbs pyinstaller==3.4

Tested on Mac OS High Sierra (10.13.6) and Mac OS Mojave (10.15.4) with .mp4 and .avi files

# Executing and compiling
_Execute_: fbs run\
_Compile_: fbs freeze or fbs release

# Troubleshooting
If "Can not find path ./libshiboken2.abi3.5.14.dylib" error on fbs freeze:\
given <SITE_PACKAGES> as "~/.conda/envs/<YOUR_ENV>/lib/python3.6/site-packages" path, copy <SITE_PACKAGES>/shiboken2/libshiboken2.abi3.5.14.dylib file both to <SITE_PACKAGES>/PyInstaller/hooks/ and <SITE_PACKAGES>/PySide2/ folders.