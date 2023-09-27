# Professor Layton and the Lost Future (5294) Reverse-Engineering
<i>(Professor Layton and the Unwound Future (5200) in America)</i>
<br><b>This has been replaced by madhatter which has the same capabilities but comes with support for saner image formats and NDS decompression. This remains as a reference, please use that instead!</b>

<br>By default, scripts expect uncompressed assets. There is code available for decompression but it needs to be called.

### Scripts
* <b>asset_image</b> for converting animations or backgrounds to PNGs or creating backgrounds
* <b>asset</b> for extracting or creating LPC2 containers
* <b>asset_script</b> for parsing LSCR script files

### Format Progression
* <b>LIMG</b> - Complete, should extract majority of files including edge cases
* <b>CANI</b> - Complete, can extract full frames of images
* <b>LPCK</b> - Complete
* <b>LSCR</b> - Complete, can print all commands

### Credits
* Tinke and DSDecmp for NDS decompression routines

### Requirements
* ndspy
* Pillow
