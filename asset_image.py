import math
from PIL import Image
from os import path

try:
    from . import binary
    from .asset import File
    from .asset import LaytonPack2
    from .asset_script import LaytonScript
except ImportError:
    import binary
    from asset import File
    from asset import LaytonPack2
    from asset_script import LaytonScript

EXPORT_EXTENSION        = "png"
EXPORT_WITH_ALPHA       = True  # Not recommended for in-engine as masking is faster
EXPORT_EXPANDED_COLOUR  = True
PROCESS_AS_PALETTED     = True

def pilPaletteToRgbTriplets(image):
    paletteData = image.getpalette()
    output = []
    for rgbTriplet in range(256):
        output.append((paletteData[rgbTriplet * 3], paletteData[rgbTriplet * 3 + 1], paletteData[rgbTriplet * 3 + 2]))
    return output

def countPilPaletteColours(image):
    lastColour = None
    for indexColour, colour in enumerate(pilPaletteToRgbTriplets(image)):
        if lastColour == colour:
            return indexColour
        lastColour = colour
    return 256

class Colour():
    def __init__(self, r = 1, g = 1, b = 1):
        self.r, self.g, self.b = r, g, b
    
    @staticmethod
    def fromInt(encodedColour):
        colourOut = Colour()
        colourOut.b = ((encodedColour >> 10) & 0x1f) / 31
        colourOut.g = ((encodedColour >> 5) & 0x1f) / 31
        colourOut.r = (encodedColour & 0x1f) / 31
        return colourOut
    
    def toList(self):
        if EXPORT_EXPANDED_COLOUR:
            return ([int(self.r * 255), int(self.g * 255), int(self.b * 255)])
        return ([int(self.r * 248), int(self.g * 248), int(self.b * 248)])

class Tile():
    def __init__(self, data=None):
        self.data = data
        self.glb = (0,0)
        self.offset = (0,0)
        self.res = (8,8)
    
    def fetchData(self, reader, bpp):
        self.offset = (reader.readU2(), reader.readU2())
        self.res = (2 ** (3 + reader.readU2()), 2 ** (3 + reader.readU2()))
        self.data = reader.read(int(bpp / 8 * self.res[0] * self.res[1]))

    def decodeToPil(self, palette, bpp):
        image = Image.new("P", self.res)
        image.putpalette(palette)
        pixelY = -1
        pixelX = 0
        for indexPixel in range(int(self.res[0] * self.res[1] * (bpp/8))):
            pixelByte = self.data[indexPixel]
            if indexPixel % int(self.res[0] * bpp/8) == 0:
                pixelY += 1
                pixelX = 0
            for _indexSubPixel in range(int(1/(bpp/8))):
                image.putpixel((pixelX, pixelY), (pixelByte & ((2**bpp) - 1)) % (len(palette) // 3))
                pixelByte = pixelByte >> bpp
                pixelX += 1
        return image

class LaytonBackgroundImage(File):

    COLOUR_MAX = 250    # Anything above 250 causes graphical corruption
    COLOUR_ALPHA = [224,0,120]

    def __init__(self):
        File.__init__(self)
        self.imageAtlas = None
        self.subImages = []
        self.subImageCropRegions = []
    
    @staticmethod
    def fromPil(image):
        """Create a new background from a PIL-based RGBA/RGB image.
        \nAll transparency must be represented in the alpha channel of the image.
        Any blending will be converted to alpha masking.
        
        Arguments:
            image {PIL.Image} -- Image in P, RGB or RGBA mode
        """

        def addAlphaToOutputImageAndRescaleColour():
            countColours = countPilPaletteColours(output.image)
            if countColours > LaytonBackgroundImage.COLOUR_MAX - 1:
                countColours = LaytonBackgroundImage.COLOUR_MAX - 1
            output.image = Image.eval(output.image, (lambda p: p + 1))    # Shift palette to make room for alpha
            tempPalette = LaytonBackgroundImage.COLOUR_ALPHA
            for channel in output.image.getpalette()[0:countColours * 3]:
                tempPalette.append(channel << 3)
            tempPalette.extend(tempPalette[-3:] * (256 - (len(tempPalette) // 3)))
            output.image.putpalette(tempPalette)

        output = LaytonBackgroundImage()
        
        if image.mode in ["P", "RGB", "RGBA"]:
            # Validate if transparency pathway required because it is slow
            if image.mode == "P":       # Detect transparency in paletted images
                if image.info.get("transparency", None) != None:
                    image = image.convert("RGBA")   # TODO: Hunt in palette for whether transparent colour is used
                else:
                    image = image.convert("RGB")
            if image.mode == "RGBA":    # Validate if image is actually transparent
                if image.getextrema()[3][0] == 255:
                    image = image.convert("RGB")
            
            alphaPix = []
            # Strict, but ensures alpha is always preserved even for tiny palettes and/or small details
            if image.mode == "RGBA":
                # Produce a 5-bit version of the image with crushed alpha ready for mixing
                reducedImage = Image.eval(image.convert('RGB'), (lambda p: p >> 3)).convert("RGBA")
                reducedImage.putalpha(Image.eval(image.split()[-1], (lambda p: int((p >> 7) * 255))))

                colours = {}
                colourSurfaceX = 0
                for x in range(image.size[0]):
                    for y in range(image.size[1]):
                        r,g,b,a = reducedImage.getpixel((x,y))
                        if a > 0:
                            if (r,g,b) not in colours.keys():
                                colours[(r,g,b)] = 1
                            else:
                                colours[(r,g,b)] += 1
                            colourSurfaceX += 1
                        else:
                            alphaPix.append((x,y))
                
                # Produce new palette from used colour strip
                palette = Image.new('RGB', (colourSurfaceX, 1))
                colourSurfaceX = 0
                averageColour = [0,0,0]
                for colour in colours.keys():
                    for indexPixel in range(colours[colour]):
                        palette.putpixel((colourSurfaceX + indexPixel, 0), colour)
                    colourSurfaceX += colours[colour]
                    averageColour[0], averageColour[1], averageColour[2] = averageColour[0] + (colour[0] * colours[colour]), averageColour[1] + (colour[1] * colours[colour]), averageColour[2] + (colour[2] * colours[colour])
                palette = palette.quantize(colors=LaytonBackgroundImage.COLOUR_MAX - 1)
                averageColour = (averageColour[0] // colourSurfaceX, averageColour[1] // colourSurfaceX, averageColour[2] // colourSurfaceX)

                # Reduce colour bleeding on alpha edges by producing a new image with alpha given the average colour
                alphaCoverage = Image.new("RGB", image.size, averageColour)
                alphaCoverage.paste(reducedImage, (0,0), mask=reducedImage)

                # Finally quantize image
                output.image = alphaCoverage.convert("RGB").quantize(palette=palette)   
            else:
                # Quantize image if no pre-processing is required
                output.image = Image.eval(image, (lambda p: p >> 3)).quantize(colors=LaytonBackgroundImage.COLOUR_MAX - 1)
            
            addAlphaToOutputImageAndRescaleColour()
            for alphaLoc in alphaPix: # TODO - Reusing alphaCoverage mask and then overlaying it may be faster
                output.image.putpixel(alphaLoc, 0)

            if output.image.size[0] % 8 != 0 or output.image.size[1] % 8 != 0:  # Align image to block sizes by filling with transparency
                tempOriginalImage = output.image
                tempScaledDimensions = (math.ceil(output.image.size[0] / 8) * 8, math.ceil(output.image.size[1] / 8) * 8)
                output.image = Image.new(tempOriginalImage.mode, tempScaledDimensions, color=0)
                output.image.putpalette(tempOriginalImage.getpalette())
                output.image.paste(tempOriginalImage, (0,0))

        # TODO - Exception on None
        return output

    def save(self):
        writer = binary.BinaryWriter()
        countColours = countPilPaletteColours(self.image)
        writer.writeU4(countColours)
        for colour in pilPaletteToRgbTriplets(self.image)[0:countColours]:
            r,g,b = colour
            tempEncodedColour = (b << 7) + (g << 2) + (r >> 3)
            writer.writeU2(tempEncodedColour)

        tiles = []
        tilemap = []
        tileOptimisationMap = self.image.resize((self.image.size[0] // 8 , self.image.size[1] // 8), resample=Image.BILINEAR)
        tileOptimisationMap = tileOptimisationMap.quantize(colors=256)
        tileOptimisationDict = {}

        for yTile in range(self.image.size[1] // 8):
            # TODO - Evaluate each tile for any similar tiles
            for xTile in range(self.image.size[0] // 8):
                tempTile = self.image.crop((xTile * 8, yTile * 8, (xTile + 1) * 8, (yTile + 1) * 8))
                if tempTile in tiles:
                    tilemap.append(tiles.index(tempTile))
                else:
                    tilemap.append(len(tiles))
                    tiles.append(tempTile)
        
        writer.writeU4(len(tiles))
        for tile in tiles:
            writer.write(tile.tobytes())
        
        writer.writeU2(self.image.size[0] // 8)
        writer.writeU2(self.image.size[1] // 8)
        for key in tilemap:
            writer.writeU2(key)

        self.data = writer.data

    def load(self, data):
        reader = binary.BinaryReader(data=data)
        if reader.read(4) == b'LIMG':
            lengthHeader        = reader.readU4()

            offsetSubImageData  = reader.readU2()
            countSubImage       = reader.readU2()

            offsetImageParam    = reader.readU2()

            reader.seek(2, 1) # UNK
            
            offsetTableTile     = reader.readU2()
            lengthTableTile     = reader.readU2()
            offsetTile          = reader.readU2()
            countTile           = reader.readU2()
            countPalette        = reader.readU2() # Always 1
            lengthPalette       = reader.readU2()
            resolution          = (reader.readU2(), reader.readU2())
            
            bpp = math.ceil(math.ceil(math.log(lengthPalette, 2)) / 4) * 4

            reader.seek(offsetSubImageData)
            for _subImageCount in range(countSubImage):
                self.subImageCropRegions.append((reader.readUInt(1) * 8, reader.readUInt(1) * 8, reader.readUInt(1) * 8, reader.readUInt(1) * 8))
                reader.seek(4,1)

            reader.seek(lengthHeader)
            palette = []
            for _indexColour in range(lengthPalette):
                palette.extend(Colour.fromInt(reader.readU2()).toList())
            
            self.imageAtlas = Image.new("P", resolution)
            self.imageAtlas.putpalette(palette)
            self.imageAtlas.paste(0, (0,0,resolution[0],resolution[1]))

            reader.seek(offsetTile)
            tilePilMap = {}
            for index in range(countTile):
                tilePilMap[index] = Tile(data=reader.read(int((bpp * 64) / 8))).decodeToPil(palette, bpp)

            reader.seek(offsetTableTile)
            width, height = self.imageAtlas.size
            for y in range(height // 8):
                for x in range(width // 8):
                    tempSelectedTile = reader.readU2()
                    tileSelectedIndex = tempSelectedTile & (2 ** 10 - 1)
                    tileSelectedFlipX = tempSelectedTile & (2 ** 11)
                    tileSelectedFlipY = tempSelectedTile & (2 ** 10)

                    if tileSelectedIndex < (2 ** 10 - 1):
                        tileFocus = tilePilMap[tileSelectedIndex % countTile]
                        if tileSelectedFlipX:
                            tileFocus = tileFocus.transpose(method=Image.FLIP_LEFT_RIGHT)
                        if tileSelectedFlipY:
                            tileFocus = tileFocus.transpose(method=Image.FLIP_TOP_BOTTOM)
                        self.imageAtlas.paste(tileFocus, (x*8, y*8))
        else:
            print("Failed magic test!")
    
    def cutSubImages(self):
        if self.imageAtlas != None:
            transparentAtlas = self.getTransparentAtlas()
            for cropDim in self.subImageCropRegions:
                left, upper, width, height = cropDim
                self.subImages.append(transparentAtlas.crop((left, upper, left + width, upper + height)))

    def exportAtlas(self, filename):
        if self.imageAtlas != None:
            self.imageAtlas.save(path.splitext(filename)[0] + "." + EXPORT_EXTENSION)
    
    def getTransparentAtlas(self):
        if self.imageAtlas != None:
            palette = pilPaletteToRgbTriplets(self.imageAtlas)
            alphaColour = palette[0]
            width, height = self.imageAtlas.size
            output = self.imageAtlas.convert("RGBA")
            for x in range(width):
                for y in range(height):
                    r,g,b,a = output.getpixel((x,y))
                    if (r,g,b) == alphaColour:
                        a = 0
                    output.putpixel((x,y), (r,g,b,a))
            return output
        return None

    def export(self, filename):
        self.cutSubImages()
        for indexSubImage, subImage in enumerate(self.subImages):
            subImage.save(path.splitext(filename)[0] + "_" + str(indexSubImage) + "." + EXPORT_EXTENSION)

class LaytonAnimatedImage(File):
    def __init__(self):
        self.frames = {}
    
    def load(self, data):
        
        scriptAnim = None
        atlasesAnim = {}
        packAnim = LaytonPack2()

        if packAnim.load(data):
            for file in packAnim.files:
                if file.name.split(".")[-1] == "lbin":
                    scriptAnim = LaytonScript()
                    scriptAnim.load(file.data)
                else:
                    atlasAnim = LaytonBackgroundImage()
                    atlasAnim.load(file.data)
                    atlasesAnim[file.name] = atlasAnim
        
        if scriptAnim != None:
            tempFrame = None
            tempName = None
            countImages = 0
            atlasesAsIndex = {}
            for command in scriptAnim.commands:
                if command.opcode == b'\xf2\x03':
                    atlasesAnim[command.operands[0].value].cutSubImages()
                    atlasesAsIndex[countImages] = atlasesAnim[command.operands[0].value]
                    countImages += 1
                elif command.opcode == b'\xfc\x03':
                    tempName = command.operands[0].value
                    tempFrame = Image.new("RGBA", (command.operands[3].value,
                                                   command.operands[4].value))
                    # TODO : Offset not implemented
                elif command.opcode == b'\xfe\x03':
                    targetSubImage = atlasesAsIndex[command.operands[0].value].subImages[command.operands[1].value]
                    tempFrame.paste(targetSubImage, (command.operands[2].value, command.operands[3].value), targetSubImage)
                    # TODO : Another UNK
                    # TODO : alpha_composite
                elif command.opcode == b'\xfd\x03':
                    self.frames[tempName] = tempFrame
    
    def export(self, filename):
        for frameName in list(self.frames.keys()):
            self.frames[frameName].save(path.splitext(filename)[0] + "_" + frameName + "." + EXPORT_EXTENSION)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1].split(".")[-1] == "cani":
            testImage = LaytonAnimatedImage()
        else:
            testImage = LaytonBackgroundImage()
        testImage.load(binary.BinaryReader(filename=sys.argv[1]).data)
        testImage.export(".".join(sys.argv[1].split(".")[:-1]))