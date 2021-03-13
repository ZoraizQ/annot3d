
import numpy as np
import os
from PIL import Image

from AnnotationSpace3D import AnnotationSpace3D

from kivy.app import App
from kivy.config import Config
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics import Color, Ellipse, Line
from kivy.graphics.texture import Texture
from kivy.graphics.vertex_instructions import Rectangle
from kivy.lang import Builder
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, BooleanProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.widget import Widget


def read_tiff(path): # returns tiff image stack as np array
    img = Image.open(path)
    slides_xy = []
    slides_xz = []
    slides_yz = []

    for i in range(img.n_frames): #x-y plane
        img.seek(i)  
        slides_xy.append(np.array(img))

    slides_xy = np.array(slides_xy)

    for npimg in np.swapaxes(slides_xy, 0, 1): # x with z, x-z plane
        slides_xz.append(npimg)

    for npimg in np.swapaxes(slides_xy, 0, 2): # x with y, y-z plane
        slides_yz.append(npimg)

    return slides_xy, slides_xz, slides_yz


def load_source_file(filename):
    global slides, npimages, w, h, d, annot3D, plane_data, num_slides, slide_annotations

    slides['xy'], slides['xz'], slides['yz'] = read_tiff(filename)
    npimages = slides['xy']
    w = npimages[0].shape[0]
    h = npimages[0].shape[1]
    d = npimages.shape[0]
    annot3D = AnnotationSpace3D(npimages, (d, w, h), color)

    plane_data = {
        'xy': {'w': w, 'h': h, 'd': d},
        'xz': {'w': d, 'h': h, 'd': w},
        'yz': {'w': w, 'h': d, 'd': h}
    }

    num_slides = plane_data[p]['d']

    slide_annotations = {
        'xy': [[] for i in range(d)], 
        'xz': [[] for i in range(w)], 
        'yz': [[] for i in range(h)]
    }


def apply_contrast(npslice, f):
    minval = np.percentile(npslice, f) # vary threshold between 1st and 99th percentiles, when f=1
    maxval = np.percentile(npslice, 100-f)
    result = np.clip(npslice, minval, maxval)
    result = ((result - minval) / (maxval - minval)) * 1024
    return (result).astype(np.short)


def apply_brightness(npslice, f):
    return (npslice*f).astype(np.short)



w, h, d = 500, 500, 25
p = 'xy' # xy initially, yz, xz
slides={}
plane_data = {}
slide_annotations = {}
current_slide = {'xy': 0, 'xz': 0, 'yz': 0}
num_slides = 0
annot3D = -1
npimages = -1


color = "#FF0000"
eraser_on = False
brush_size = 5
eraser_size = 5
global_contrast = 1
global_brightness = 15


Config.set('graphics', 'width', str(w+d+20*3+110))
Config.set('graphics', 'height', str(w+d+20*3))
Config.write()



class LoadDialog(FloatLayout):
    load = ObjectProperty(None)
    cancel = ObjectProperty(None)


class SaveDialog(FloatLayout):
    save = ObjectProperty(None)
    text_input = ObjectProperty(None)
    cancel = ObjectProperty(None)

class ExportDialog(FloatLayout):
    export = ObjectProperty(None)
    text_input = ObjectProperty(None)
    cancel = ObjectProperty(None)
    plane = StringProperty('xy')


class PCanvas(Widget):
    dx = NumericProperty(0)
    dy = NumericProperty(0)
    gzoomfactor = NumericProperty()
    bg_tex = ObjectProperty()
    annot_tex = ObjectProperty()
    hidden = BooleanProperty(False)
    init_anchor_x = ''
    init_anchor_y = ''
    p = ''

    def render(self, plane, image):
        global current_slide, annot3D
        self.dx, self.dy = image.shape
        self.p = plane

        self.init_anchor_x = self.parent.anchor_x
        self.init_anchor_y = self.parent.anchor_y

        self.bg_tex = Texture.create(size=(self.dy, self.dx))
        data = image.tobytes()
        self.bg_tex.blit_buffer(data, colorfmt='luminance', bufferfmt='short')


        self.annot_tex = Texture.create(size=(self.dy, self.dx))
        d = current_slide[self.p]
        empty_data = annot3D.get_slice(self.p, d).tobytes()
        self.annot_tex.blit_buffer(empty_data, colorfmt='rgba', bufferfmt='ubyte')
            

    def change_bg(self, image):
        data = image.tobytes()
        self.bg_tex.blit_buffer(data, colorfmt='luminance', bufferfmt='short')


    def change_annot(self, image):
        data = image.tobytes()
        self.annot_tex.blit_buffer(data, colorfmt='rgba', bufferfmt='ubyte')
        self.canvas.ask_update()


    def on_touch_down(self, touch):
        global annot3D, current_slide, p
       
        if self.collide_point(*touch.pos) and self.p == p:
            annot3D.save_history(self.p, current_slide[self.p]) # save history after every line stroke
                

    def on_touch_move(self, touch): # PAINT
        global eraser_on, p, annot3D, current_slide, color, brush_size, eraser_size
        
        if self.collide_point(*touch.pos) and self.p == p:
            x = (touch.x-self.pos[0])/self.gzoomfactor
            y = (touch.y-self.pos[1])/self.gzoomfactor
            d = current_slide[self.p]

            if (eraser_on): 
                annot3D.draw(self.p, d, x, y, eraser_size, 0, [0,0,0,0])
            else:
                annot3D.draw(self.p, d, x, y, brush_size, 1, [255, 0, 0, 255])

            self.change_annot(annot3D.get_slice(self.p, d))


    def focus(self, focus):
        if focus:
            self.parent.anchor_x = 'center'
            self.parent.anchor_y = 'center'
        else:
            self.parent.anchor_x = self.init_anchor_x
            self.parent.anchor_y = self.init_anchor_y

    def hide(self, hide):
        self.hidden = hide

    def on_touch_up(self, touch):
        pass




class MainScreen(Screen):
    c = {'xy': 0, 'xz': 0, 'yz': 0}

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self._keyboard = Window.request_keyboard(self._keyboard_closed, self)
        self._keyboard.bind(on_key_down=self._on_keyboard_down)

    def _keyboard_closed(self):
        self._keyboard.unbind(on_key_down=self._on_keyboard_down)
        self._keyboard = None

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        try:
            if keycode[1] == 'left':
                self.slide_left()


            elif keycode[1] == 'right':
                self.slide_right()

            elif keycode[1] == '1':
                self.switch_plane('xy')
                if 'ctrl' in modifiers:
                    self.focus_plane('xy')
                else:
                    self.reset_focus()

            elif keycode[1] == '2':
                self.switch_plane('xz')
                if 'ctrl' in modifiers:
                    self.focus_plane('xz')
                else:
                    self.reset_focus()

            elif keycode[1] == '3':
                self.switch_plane('yz')
                if 'ctrl' in modifiers:
                    self.focus_plane('yz')
                else:
                    self.reset_focus()

            elif keycode[1] == 'r':
                self.render_volume()

            elif keycode[1] == 'b':
                self.select_brush()

            elif keycode[1] == 'e':
                self.select_eraser()

            elif keycode[1] == 't':
                self.predict_slide()

            elif keycode[1] == '5':
                print("Predicting multiple slides...")
                self.predict_slide(num_slides=10)

            elif keycode[1] == '-': # secret hotkey to autoload src
                self.load_src('', ['data/src.tiff'])

            elif keycode[1] == '=': # secret hotkey to autoload src and annot
                self.load_annot('', ['data/annot'])
            
            elif keycode[1] == 'w': # secret hotkey to autoload weights
                self.load_model_weights('', ['model_weights/unet_neurons.hdf5'])

            elif keycode[1] == 'z' and 'ctrl' in modifiers:
                self.undo()
            
            elif keycode[1] == 's' and 'ctrl' in modifiers:
                self.show_save()

            elif keycode[1] == 'o' and 'ctrl' in modifiers:
                self.show_load(True)
            
            elif keycode[1] == 'l' and 'ctrl' in modifiers:
                self.show_load()

        except:
            pass

        return True


    def switch_plane(self, plane):
        global p, num_slides, slides, current_slide
        
        p = plane
        num_slides = plane_data[p]['d']
        self.ids.current_slide_label.text = p + ': ' + str(current_slide[p]+1)
        self.change_slide(0)


    def focus_plane(self, curr_p):
        for p in ['xy', 'xz', 'yz']:
            if p == curr_p:
                self.c[p].focus(True)
                self.c[p].hide(False)
            else:
                self.c[p].focus(False)
                self.c[p].hide(True)

    def reset_focus(self):
        for p in ['xy', 'xz', 'yz']:
            self.c[p].focus(False)
            self.c[p].hide(False)

    def slide_left(self):
        global current_slide, p
        if (current_slide[p] > 0):
            self.change_slide(-1)


    def slide_right(self):
        global current_slide, p
        if (current_slide[p] < num_slides-1):
            self.change_slide(1)


    def change_slide(self, step):
        global current_slide, p, annot3D, slides
        
        current_slide[p] += step
        d = current_slide[p]

        self.ids.current_slide_label.text = p + ': ' + str(d+1)

        self.c[p].change_bg(slides[p][d])
        self.c[p].change_annot(annot3D.get_slice(p, d))

        self.change_gfilter()


    def change_gfilter(self):
        global slides, current_slide, npimages, global_contrast, global_brightness

        for ax in ['xy','xz','yz']:
            # new np slices produced from filter effects
            np_slice = None
            cs = current_slide[ax]
            
            if (ax == 'xy'):
                np_slice = npimages[cs]
            elif (ax == 'xz'):
                np_slice = np.swapaxes(npimages, 0, 1)[cs]
            elif (ax == 'yz'):
                np_slice = np.swapaxes(npimages, 0, 2)[cs]

            np_slice = apply_contrast(np_slice, global_contrast)
            np_slice = apply_brightness(np_slice, global_brightness)
            
            self.c[ax].change_bg(np_slice)

    
    def predict_slide(self, num_slides=None):
        global annot3D, p, current_slide, w, h, d
        if p == 'xz': # make the model predictions work only for xz plane which it is trained on
            if num_slides is None:
                annot3D.model_predict(p, current_slide[p])
                self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))
            else:
                for i in range(num_slides):
                    if current_slide[p]+i >= w: # does not exceed xz slide range
                        break

                    annot3D.model_predict(p, current_slide[p]+i)
                    self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]+i))


    def clear(self):
        global annot3D, p, current_slide
        annot3D.clear_slice(p, current_slide[p])
        self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))


    def undo(self):
        global annot3D, p, current_slide
        annot3D.undo_history()
        self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))

    def dismiss_popup(self):
        self._popup.dismiss()

    def show_load(self, file_type='annot'):
        dialog = -1
        title = ""
        if (file_type == 'src'):
            dialog = LoadDialog(load=self.load_src, cancel=self.dismiss_popup)
            title = "Load source TIFF"
        elif (file_type == 'annot'):
            dialog = LoadDialog(load=self.load_annot, cancel=self.dismiss_popup)
            title = "Load annotation file (no extension)"
        elif (file_type == 'model_weights'): 
            dialog = LoadDialog(load=self.load_model_weights, cancel=self.dismiss_popup)
            title = "Load model weights (hdf5)"

        self._popup = Popup(title=title, content=dialog, size_hint=(0.9, 0.9))
        self._popup.open()


    def load_src(self, path, filename):
        global slides
        load_source_file(filename[0])

        self.c['xy'] = self.ids.canvas_xy
        self.c['xz'] = self.ids.canvas_xz
        self.c['yz'] = self.ids.canvas_yz

        self.c['xz'].render('xz', slides['xz'][0])
        self.c['yz'].render('yz', slides['yz'][0])
        self.c['xy'].render('xy', slides['xy'][0])
        
        self.change_gfilter()
        self.dismiss_popup()


    def load_annot(self, path, filename):
        global annot3D, p, current_slide
        annot3D.load(filename[0])
        self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))
        self.dismiss_popup()


    def load_model_weights(self, path, filename):
        annot3D.load_model_weights(filename[0])
        self.dismiss_popup()


    def merged_load(self):
        global annot3D, p, current_slide
        # annot3D.mergeload(path_list)
        pass

    def show_save(self):
        dialog = SaveDialog(save=self.save, cancel=self.dismiss_popup)
        self._popup = Popup(title="Save annotation file", content=dialog, size_hint=(0.9, 0.9))
        self._popup.open()

    def save(self, path, filename):
        global annot3D
        annot3D.save(os.path.join(path,filename))
        self.dismiss_popup()

    def show_export(self):
        dialog = ExportDialog(export=self.export, cancel=self.dismiss_popup)
        self._popup = Popup(title="Export data directory", content=dialog, size_hint=(0.9, 0.9))
        self._popup.open()

    def export(self, path, filename, plane):
        global annot3D
        annot3D.export(os.path.join(path,filename), plane)
        self.dismiss_popup()

    def render_volume(self):
        global annot3D
        annot3D.plot3D()

    def select_eraser(self):
        global eraser_on
        eraser_on = True

    def select_brush(self):
        global eraser_on
        eraser_on = False
    
    def change_brush_size(self,*args):
        global brush_size 
        brush_size = args[1]

    def change_eraser_size(self,*args):
        global eraser_size 
        eraser_size = args[1]

    def change_global_brightness(self,*args):
        global global_brightness 
        global_brightness = args[1]
        self.change_gfilter()

    def change_global_contrast(self,*args):
        global global_contrast 
        global_contrast = args[1]
        self.change_gfilter()
    

class ScreenManagement(ScreenManager):
    pass



class AnnotationToolbox3D(App):

    def build(self):
        self.root = Builder.load_file("toolbox.kv")
        return self.root


Factory.register('LoadDialog', cls=LoadDialog)
Factory.register('SaveDialog', cls=SaveDialog)
Factory.register('ExportDialog', cls=ExportDialog)

if __name__ == '__main__':
    AnnotationToolbox3D().run()
    
