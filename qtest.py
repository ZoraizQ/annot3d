from PySide2.QtUiTools import QUiLoader
from PySide2.QtCore import QCoreApplication, QEvent, QSize, QMetaObject, Qt, SLOT, Slot
from PySide2.QtGui import QBitmap, QColor, QCursor, QIcon, QImage, QKeySequence, QPainter, QPalette, QPixmap
from PySide2.QtWidgets import QApplication, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDial, QDoubleSpinBox, QFileDialog, QFontComboBox, QGraphicsGridLayout, QGraphicsOpacityEffect, QHBoxLayout, QLCDNumber, QLabel, QLineEdit, QMainWindow, QMenu, QProgressBar, QPushButton, QRadioButton, QSlider, QSpinBox, QStatusBar, QTimeEdit, QToolBar, QGridLayout, QVBoxLayout, QWidget, QAction, QShortcut


from traits.api import HasTraits, Instance, on_trait_change, Range
from traitsui.api import View, Item
from mayavi.core.ui.api import MayaviScene, MlabSceneModel, SceneEditor
from mayavi import mlab


import numpy as np
import os
from PIL import Image, ImageQt
from AnnotationSpace3D import AnnotationSpace3D
import random
import sys
import matplotlib.pyplot as plt
from helpers import read_tiff, apply_contrast, apply_brightness, disk


COLORS = {
    '#ff0000': [255, 0, 0, 255],
    '#35e3e3': [53, 227, 227, 255],
    '#5ebb49': [94, 187, 73, 255],
    '#ffd035': [255, 208, 53, 255],
}

ERASER_COLOR_RGBA = [255, 255, 255, 255]
INIT_COLOR_RGBA = COLORS['#ff0000']

p = 'xy' # xy initially, yz, xz
current_slide = {'xy': 0, 'xz': 0, 'yz': 0}
annot3D = -1
w, h, d = 500, 500, 25
eraser_on = False
brush_size = 5
eraser_size = 5
global_contrast = 1
global_brightness = 15
global_annot_opacity = 0.8


def get_filled_pixmap(pixmap_file):
    pixmap = QPixmap(pixmap_file)
    mask = pixmap.createMaskFromColor(QColor('black'), Qt.MaskOutColor)
    pixmap.fill((QColor('white')))
    pixmap.setMask(mask)
    return pixmap


def get_circle_cursor(brush_size, color_rgba):
    x, y = (brush_size*2+1, brush_size*2+1)
    circle_img = np.zeros((x, y, 4))
    rr, cc = disk(center=(x//2, y//2), radius=brush_size, shape=(x, y))
    circle_img[rr, cc] = color_rgba
    image = np.require(circle_img, np.uint8, 'C')
    qimg = QImage(image.data, y, x, 4 * y , QImage.Format_RGBA8888)
    return QCursor(QPixmap(qimg))



class Visualization(HasTraits):
    scene = Instance(MlabSceneModel, ())

    @on_trait_change('scene.activated')
    def update_plot(self):
        global annot3D
        npimages = annot3D.get_npimages()
        npspace = annot3D.get_npspace()
        self.npspace_sf = mlab.pipeline.scalar_field(npspace) # scalar field to update later
        bg_original = mlab.pipeline.volume(mlab.pipeline.scalar_field(npimages))
        segmask = mlab.pipeline.iso_surface(self.npspace_sf, color=(1.0, 0.0, 0.0))
        # self.scene.scene.disable_render = False


    def update_annot(self): # update the scalar field and visualization auto updates
        npspace = annot3D.get_npspace()
        self.npspace_sf.mlab_source.trait_set(scalars=npspace) 


    view = View(Item('scene', editor=SceneEditor(scene_class=MayaviScene), height=250, width=300, show_label=False), resizable=True )



class MayaviQWidget(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.visualization = Visualization()

        self.ui = self.visualization.edit_traits(parent=self, kind='subpanel').control
        layout.addWidget(self.ui)
        self.ui.setParent(self)
    
    def update_annot(self):
        self.visualization.update_annot()



class QPaletteButton(QPushButton):
    def __init__(self, color):
        super().__init__()
        self.setFixedSize(QSize(24,24))
        self.color = color
        self.setStyleSheet("background-color: %s;" % color)



class Canvas(QWidget):

    def __init__(self, image, plane):
        super().__init__()
        global current_slide, annot3D, COLORS
        self.dx, self.dy = image.shape
        self.p = plane # plane

        self.l = QGridLayout()
        self.bg = QLabel()
        self.annot = QLabel()

        image = np.require(image, np.short, 'C')   
        qimg = QImage(image.data, self.dy, self.dx, 2 * self.dy , QImage.Format_Grayscale16)
        self.bg.setPixmap(QPixmap(qimg))

        image = np.zeros((self.dx, self.dy, 4))
        image = np.require(image, np.uint8, 'C') 
        qimg = QImage(image.data, self.dy, self.dx, 4 * self.dy , QImage.Format_RGBA8888)
        self.annot.setPixmap(QPixmap(qimg))

        self.opacity_effect = QGraphicsOpacityEffect() 
        self.opacity_effect.setOpacity(0.5) 
        self.annot.setGraphicsEffect(self.opacity_effect)


        self.l.addWidget(self.bg, 0, 0, Qt.AlignLeft | Qt.AlignTop)
        self.l.addWidget(self.annot, 0, 0, Qt.AlignRight | Qt.AlignBottom)

        self.setLayout(self.l)

        self.pen_color_rgba = INIT_COLOR_RGBA
        
        self.update_cursor()


    def update_cursor(self):
        if eraser_on:
            self.setCursor(get_circle_cursor(eraser_size, ERASER_COLOR_RGBA))
        else:
            self.setCursor(get_circle_cursor(brush_size, self.pen_color_rgba))


    def update_annot_opacity(self):
        self.opacity_effect.setOpacity(global_annot_opacity) 


    def set_pen_color(self, c):
        self.pen_color_rgba = COLORS[c]
        self.update_cursor()


    def mouseMoveEvent(self, e):   
        global current_slide, annot3D    
        x = e.x()-10
        y = e.y()-10
        
        d = current_slide[self.p]

        if (eraser_on): 
            annot3D.draw(self.p, d, x, y, eraser_size, 0, [0,0,0,0])
        else:
            annot3D.draw(self.p, d, x, y, brush_size, 1, self.pen_color_rgba)

        self.change_annot(annot3D.get_slice(self.p, d))
        self.annot.update()


    def mousePressEvent(self, e):
        annot3D.save_history(self.p, current_slide[self.p]) # save history after every line stroke
        

    def change_bg(self, image):
        image = np.require(image, np.short, 'C')        
        qimg = QImage(image.data, self.dy, self.dx, 2 * self.dy , QImage.Format_Grayscale16)
        self.bg.setPixmap(QPixmap(qimg))
        self.bg.update()


    def change_annot(self, image):
        annot = np.require(image, np.uint8, 'C') 
        qimg = QImage(annot.data, self.dy, self.dx, 4 * self.dy , QImage.Format_RGBA8888)
        self.annot.setPixmap(QPixmap(qimg))
        self.annot.update()





class MainWindow(QMainWindow):
    c = {'xy': 0, 'xz': 0, 'yz': 0}
    
    dims = (500, 500, 25) # w, h, d
    slides={}
    plane_data = {}
    slide_annotations = {}
    num_slides = 0
    npimages = -1


    def load_source_file(self, filename):
        global COLORS, p, current_slide, annot3D

        self.slides['xy'], self.slides['xz'], self.slides['yz'] = read_tiff(filename)
        self.npimages = self.slides['xy']
        
        w = self.npimages[0].shape[0]
        h = self.npimages[0].shape[1]
        d = self.npimages.shape[0]

        annot3D = AnnotationSpace3D(self.npimages, (d, w, h), INIT_COLOR_RGBA)

        self.plane_data = {
            'xy': {'w': w, 'h': h, 'd': d},
            'xz': {'w': d, 'h': h, 'd': w},
            'yz': {'w': w, 'h': d, 'd': h}
        }

        self.dims = (w, h, d)

        self.num_slides = self.plane_data[p]['d']

        self.slide_annotations = {
            'xy': [[] for i in range(d)], 
            'xz': [[] for i in range(w)], 
            'yz': [[] for i in range(h)]
        }


    def __init__(self):
        super().__init__()

    # Install an event filter to filter the touch events.
        # self.installEventFilter(self)

        
    # ANNOT LOAD UP
        self.load_source_file('data/src.tiff')

        for p in ['xy', 'xz', 'yz']:
            self.c[p] = Canvas(image=self.slides[p][0], plane=p)
            
        self.change_gfilter()

        w = QWidget()
        
        l = QHBoxLayout()
        w.setLayout(l)


    # COLOR PALETTE
        palette_layout = QGridLayout()
        i, j = 1, 1
        for c in COLORS:
            b = QPaletteButton(c)
            b.pressed.connect(lambda c=c : self.set_canvas_pen_color(c))
            palette_layout.addWidget(b, i, j)
            j += 1
            if j > 2:
                j = 1
                i += 1

        l.addLayout(palette_layout)

    # CANVAS LAYOUT
        canvas_layout = QGridLayout()
        self.slide_label = QLabel('xy: 1')
        self.slide_label.setFixedWidth(40)
        canvas_layout.addWidget(self.slide_label,1,1)
        canvas_layout.addWidget(self.c['xy'],2,2)
        canvas_layout.addWidget(self.c['xz'],1,2)
        canvas_layout.addWidget(self.c['yz'],2,1)
        l.addLayout(canvas_layout)

    # TOOLBAR, STATUSBAR, MENU

        self.statusBar()
        
        exitAction = QAction(QIcon(get_filled_pixmap('graphics/delete.png')), 'Exit', self)
        exitAction.setShortcut(QKeySequence.Quit) # Ctrl+Q
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.close)

        loadAnnotAction = QAction(QIcon(get_filled_pixmap('graphics/load.png')), 'Load annotations', self)
        loadAnnotAction.setShortcut(QKeySequence.Open) # Ctrl+O
        loadAnnotAction.setStatusTip('Load new annotations file')
        loadAnnotAction.triggered.connect(self.load_annot_dialog)

        loadWeightsAction = QAction(QIcon(get_filled_pixmap('graphics/merge.png')), 'Load model weights', self)
        loadWeightsAction.setShortcut('Ctrl+W') # Ctrl+O
        loadWeightsAction.setStatusTip('Load model weights')
        loadWeightsAction.triggered.connect(self.load_weights_dialog)

        saveAnnotAction = QAction(QIcon(get_filled_pixmap('graphics/save.png')), 'Save annotations', self)
        saveAnnotAction.setShortcut(QKeySequence.Save) # Ctrl+S
        saveAnnotAction.setStatusTip('Save annotations file')
        saveAnnotAction.triggered.connect(self.save_annots_dialog)

        exportAction = QAction(QIcon(get_filled_pixmap('graphics/render.png')), 'Export dataset', self)
        exportAction.setShortcut('Ctrl+E')
        exportAction.setStatusTip('Export source and annotations as dataset directory')
        exportAction.triggered.connect(self.export_dialog)

        selectEraserAction = QAction(QIcon(get_filled_pixmap('graphics/eraser.png')), 'Toggle Eraser', self)
        selectEraserAction.setShortcut('E')
        selectEraserAction.setStatusTip('Toggle eraser')
        selectEraserAction.setCheckable(True)
        selectEraserAction.triggered.connect(self.toggle_eraser)

        xyAction = QAction('xy', self)
        xyAction.setShortcut('1')
        xyAction.setStatusTip('Switch to xy plane')
        xyAction.triggered.connect(lambda _: self.switch_plane('xy'))

        xzAction = QAction('xz', self)
        xzAction.setShortcut('2')
        xzAction.setStatusTip('Switch to xz plane')
        xzAction.triggered.connect(lambda _: self.switch_plane('xz'))

        yzAction = QAction('yz', self)
        yzAction.setShortcut('3')
        yzAction.setStatusTip('Switch to yz plane')
        yzAction.triggered.connect(lambda _: self.switch_plane('yz'))
        

    # HIDDEN HOTKEY ACTIONS
        slideLeftAction = QAction('Left', self)
        slideLeftAction.setShortcut('Left')
        slideLeftAction.setStatusTip('Slide left')
        slideLeftAction.triggered.connect(self.slide_left)

        slideRightAction = QAction('Right', self)
        slideRightAction.setShortcut('Right')
        slideRightAction.setStatusTip('Slide right')
        slideRightAction.triggered.connect(self.slide_right)

        undoAction = QAction('Undo', self)
        undoAction.setShortcut(QKeySequence.Undo)
        undoAction.setStatusTip('Undo last annotation')
        undoAction.triggered.connect(self.undo)

        renderAction = QAction('Render', self)
        renderAction.setShortcut('R')
        renderAction.setStatusTip('Update annotation render')
        renderAction.triggered.connect(self.render)

        predictAction = QAction('Predict Current', self)
        predictAction.setShortcut('P')
        predictAction.setStatusTip('Predict for current slide')
        predictAction.triggered.connect(lambda x: self.predict_slide())


        self.addAction(slideLeftAction)
        self.addAction(slideRightAction)
        self.addAction(undoAction)
        self.addAction(renderAction)
        self.addAction(predictAction)
        
    
    # adding menubar actions 
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(loadAnnotAction)
        fileMenu.addAction(loadWeightsAction)
        fileMenu.addAction(saveAnnotAction)
        fileMenu.addAction(exportAction)
        fileMenu.addAction(exitAction)


    # SLIDERS
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setValue(global_brightness)
        self.brightness_slider.setMinimum(1)
        self.brightness_slider.setMaximum(30)
        self.brightness_slider.valueChanged.connect(self.change_brightness)

        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setValue(global_contrast)
        self.contrast_slider.setMinimum(1)
        self.contrast_slider.setMaximum(15)
        self.contrast_slider.valueChanged.connect(self.change_contrast)

        self.brush_size_slider = QSlider(Qt.Horizontal)
        self.brush_size_slider.setValue(brush_size)
        self.brush_size_slider.setMinimum(1)
        self.brush_size_slider.setMaximum(15)
        self.brush_size_slider.valueChanged.connect(self.change_brush_size)

        self.eraser_size_slider = QSlider(Qt.Horizontal)
        self.eraser_size_slider.setValue(eraser_size)
        self.eraser_size_slider.setMinimum(1)
        self.eraser_size_slider.setMaximum(15)
        self.eraser_size_slider.valueChanged.connect(self.change_eraser_size)

        self.annot_opacity_slider = QSlider(Qt.Horizontal)
        self.annot_opacity_slider.setValue(global_annot_opacity)
        self.annot_opacity_slider.setSingleStep(2) # 0.1 * scaled later
        self.annot_opacity_slider.setMinimum(2)
        self.annot_opacity_slider.setMaximum(10)
        self.annot_opacity_slider.valueChanged.connect(self.change_annot_opacity)

    # adding toolbar actions
        self.toolbar = self.addToolBar('Main')
        self.toolbar.addActions([xyAction, xzAction, yzAction, selectEraserAction])
        self.toolbar.addSeparator()
        self.toolbar.setStyleSheet("QToolBar{spacing:10px;}")
        self.toolbar.addWidget(QLabel('Brightness'))
        self.toolbar.addWidget(self.brightness_slider)
        self.toolbar.addWidget(QLabel('Contrast'))
        self.toolbar.addWidget(self.contrast_slider)
        self.toolbar.addWidget(QLabel('Brush Size'))
        self.toolbar.addWidget(self.brush_size_slider)
        self.toolbar.addWidget(QLabel('Eraser Size'))
        self.toolbar.addWidget(self.eraser_size_slider)
        self.toolbar.addWidget(QLabel('Annotation Opacity'))
        self.toolbar.addWidget(self.annot_opacity_slider)


    # MAYAVI
        container = QWidget()
        self.mayavi_widget = MayaviQWidget(container)
        l.addWidget(self.mayavi_widget)
        
        self.setWindowTitle("Annotation Toolbox 3D")

        self.setCentralWidget(w)


    def load_annot_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Load annotations file', '.')

        global annot3D, current_slide
        if fname != '':
            annot3D.load(fname)
            for p in ['xy', 'xz', 'yz']:
                self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))


    def load_weights_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Load model weights (hfd5)', '.')
        global annot3D
        if fname != '':
            annot3D.load_model_weights(fname)


    def save_annots_dialog(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Save annotations file', '.')
        global annot3D
        if fname != '':
            annot3D.save(os.path.join(fname))    


    def export_dialog(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Export dataset directory (src and annot)', '.') # here fname is folder/dir name
        global annot3D
        print(fname)
        if fname != '':
            annot3D.export(fname, 'xz')


    def update_canvas_cursors(self):
        self.c['xy'].update_cursor()
        self.c['xz'].update_cursor()
        self.c['yz'].update_cursor()


    def toggle_eraser(self):
        global eraser_on
        eraser_on = not eraser_on
        self.update_canvas_cursors()


    def change_brush_size(self):
        global brush_size 
        brush_size = self.brush_size_slider.value()
        self.update_canvas_cursors()


    def change_eraser_size(self):
        global eraser_size 
        eraser_size = self.eraser_size_slider.value()
        self.update_canvas_cursors()


    def change_annot_opacity(self):
        global global_annot_opacity 
        global_annot_opacity = self.annot_opacity_slider.value() * 0.1
        self.c['xy'].update_annot_opacity()
        self.c['xz'].update_annot_opacity()
        self.c['yz'].update_annot_opacity()


    def change_brightness(self):
        global global_brightness
        global_brightness = self.brightness_slider.value()
        self.change_gfilter()


    def change_contrast(self):
        global global_contrast
        global_contrast = self.contrast_slider.value()
        self.change_gfilter()
    

    def switch_plane(self, plane):
        global p, current_slide
        p = plane
        self.num_slides = self.plane_data[p]['d']
        self.change_slide(0)


    def render(self):
        self.mayavi_widget.update_annot()

    
    # def focus_plane(self, curr_p):
    #     for p in ['xy', 'xz', 'yz']:
    #         if p == curr_p:
    #             self.c[p].focus(True)
    #             self.c[p].hide(False)
    #         else:
    #             self.c[p].focus(False)
    #             self.c[p].hide(True)

    # def reset_focus(self):
    #     for p in ['xy', 'xz', 'yz']:
    #         self.c[p].focus(False)
    #         self.c[p].hide(False)

    def predict_slide(self, num_slides=None):
        global annot3D, p, current_slide

        if p == 'xz': # make the model predictions work only for xz plane which it is trained on
            if num_slides is None:
                annot3D.model_predict(p, current_slide[p])
                self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))
            else:
                for i in range(num_slides):
                    if current_slide[p]+i >= self.w: # does not exceed xz slide range
                        break

                    annot3D.model_predict(p, current_slide[p]+i)
                    self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]+i))




    def slide_left(self):
        global current_slide, p
        if (current_slide[p] > 0):
            self.change_slide(-1)


    def slide_right(self):
        global current_slide, p
        if (current_slide[p] < self.num_slides-1):
            self.change_slide(1)


    def change_slide(self, step):
        global current_slide, p, annot3D, slides
        
        current_slide[p] += step
        d = current_slide[p]

        self.slide_label.setText(p + ': ' + str(d+1))

        self.c[p].change_bg(self.slides[p][d])
        self.c[p].change_annot(annot3D.get_slice(p, d))

        self.change_gfilter()


    def change_gfilter(self):
        global slides, current_slide, npimages, global_contrast, global_brightness

        for ax in ['xy','xz','yz']:
            # new np slices produced from filter effects
            np_slice = None
            cs = current_slide[ax]
            
            if (ax == 'xy'):
                np_slice = self.npimages[cs]
            elif (ax == 'xz'):
                np_slice = np.swapaxes(self.npimages, 0, 1)[cs]
            elif (ax == 'yz'):
                np_slice = np.swapaxes(self.npimages, 0, 2)[cs]

            np_slice = apply_contrast(np_slice, global_contrast)
            np_slice = apply_brightness(np_slice, global_brightness)
            
            self.c[ax].change_bg(np_slice)


    def predict_slide(self, num_slides=None):
        global annot3D, p, current_slide
        if p == 'xz': # make the model predictions work only for xz plane which it is trained on
            if num_slides is None:
                annot3D.model_predict(p, current_slide[p])
                self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))
            else:
                for i in range(num_slides):
                    if current_slide[p]+i >= self.w: # does not exceed xz slide range
                        break

                    annot3D.model_predict(p, current_slide[p]+i)
                    self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]+i))

    def clear(self):
        global annot3D, p, current_slide
        annot3D.clear_slice(p, current_slide[p])
        self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))


    def undo(self):
        global annot3D, current_slide
        annot3D.undo_history()
        for p in ['xy', 'xz', 'yz']:
            self.c[p].change_annot(annot3D.get_slice(p, current_slide[p]))


    def set_canvas_pen_color(self, c):
        self.c['xy'].set_pen_color(c)
        self.c['xz'].set_pen_color(c)
        self.c['yz'].set_pen_color(c)


        


if __name__ == "__main__":
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()


    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.black)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
