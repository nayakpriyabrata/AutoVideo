"""HarfBuzz + FreeType font adapter for Pillow builds without libraqm.

Shape complete Indic runs (not individual letters), then render their glyphs.
Pillow's ImageDraw API can use this scalable adapter like a regular font.
"""
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


class IndicFont:
    def __init__(self, path, size, bold=True):
        import uharfbuzz as hb
        import freetype
        self.size = int(size)
        self.path = str(path)
        self._ft = freetype.Face(self.path)
        self._ft.set_pixel_sizes(0,self.size)
        data = Path(path).read_bytes()
        self._hb = hb.Font(hb.Face(data))
        self._hb.scale=(self.size*64,self.size*64)
        self._hb.set_variations({'wght':650 if bold else 500, 'wdth':100})
        try:
            info=self._ft.get_variation_info()
            self._ft.set_var_design_coords([(650 if bold else 500) if axis.tag=='wght' else axis.default for axis in info.axes])
        except (AttributeError,ValueError):
            pass
        self._freetype = freetype
        # Cache rendered text per font instance. A class-level lru_cache on a
        # method keeps each `self` alive in its global cache until eviction.
        self._render_cache = OrderedDict()

    def getname(self):
        return (self._ft.family_name.decode(),self._ft.style_name.decode())

    def _shape(self,text):
        import uharfbuzz as hb
        buffer=hb.Buffer();buffer.add_str(str(text));buffer.guess_segment_properties()
        hb.shape(self._hb,buffer)
        return list(zip(buffer.glyph_infos,buffer.glyph_positions))

    def getlength(self,text,*args,**kwargs):
        return sum(position.x_advance for _,position in self._shape(text))/64

    def _render(self,text,stroke):
        key=(str(text),int(stroke))
        if key in self._render_cache:
            self._render_cache.move_to_end(key)
            return self._render_cache[key]
        rendered=self._render_uncached(*key)
        self._render_cache[key]=rendered
        if len(self._render_cache)>256:
            self._render_cache.popitem(last=False)
        return rendered

    def _render_uncached(self,text,stroke):
        glyphs=[];x=y=0
        for info,pos in self._shape(text):
            self._ft.load_glyph(info.codepoint,self._freetype.FT_LOAD_RENDER)
            slot=self._ft.glyph;bitmap=slot.bitmap
            px=int(round((x+pos.x_offset)/64))+slot.bitmap_left
            py=-int(round((y+pos.y_offset)/64))-slot.bitmap_top
            if bitmap.rows and bitmap.width:
                # FreeType grayscale pitch can include padding.
                raw=np.array(bitmap.buffer,dtype=np.uint8).reshape(bitmap.rows,abs(bitmap.pitch))[:,:bitmap.width]
                glyphs.append((px,py,Image.fromarray(raw,'L')))
            x+=pos.x_advance;y+=pos.y_advance
        if not glyphs:
            return Image.new('L',(max(1,int(self.getlength(text))),1)),(0,0,0,0)
        left=min(px for px,py,im in glyphs)-stroke
        top=min(py for px,py,im in glyphs)-stroke
        right=max(px+im.width for px,py,im in glyphs)+stroke
        bottom=max(py+im.height for px,py,im in glyphs)+stroke
        result=Image.new('L',(right-left,bottom-top))
        for px,py,image in glyphs:
            layer=Image.new('L',result.size);layer.paste(image,(px-left,py-top))
            from PIL import ImageChops
            result=ImageChops.lighter(result,layer)
        if stroke:
            result=result.filter(ImageFilter.MaxFilter(stroke*2+1))
        return result,(left,top,right,bottom)

    def getbbox(self,text,mode='',direction=None,features=None,language=None,
                stroke_width=0,anchor=None,**kwargs):
        return self._render(str(text),int(stroke_width))[1]

    def getmask2(self,text,mode='',fill=None,direction=None,features=None,language=None,
                 stroke_width=0,anchor=None,ink=0,start=None,**kwargs):
        image,box=self._render(str(text),int(stroke_width))
        return image.im,(box[0],box[1])

    def getmask(self,text,mode='',**kwargs):
        return self.getmask2(text,mode,**kwargs)[0]
