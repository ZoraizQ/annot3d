import sys
from tkinter import *
from tkinter.colorchooser import askcolor
import numpy as np
from scipy import ndimage
import PIL
from tkinter import ttk 
from tkinter.filedialog import asksaveasfile, askopenfile, askopenfilenames
from PIL import ImageTk, Image, ImageSequence, ImageEnhance, ImageFilter, ImageDraw
import io
from os import path, name
from AnnotationSpace3D import AnnotationSpace3D


def read_tiff(path): # returns tiff image stack as np array
	
	img = Image.open(path)
	npimages = []
	photoimages_xy = []
	photoimages_xz = []
	photoimages_yz = []
	
	for i in range(img.n_frames): #x-y plane
		img.seek(i)        
		npimages.append(np.array(img)/15)
		photoimages_xy.append(ImageTk.PhotoImage(image=Image.fromarray(npimages[i])))
	
	npimages = np.array(npimages)

	for img in np.swapaxes(npimages, 0, 1): # x with z, x-z plane
		photoimages_xz.append(ImageTk.PhotoImage(image=Image.fromarray(img)))

	for img in np.swapaxes(npimages, 0, 2): # x with y, y-z plane
		photoimages_yz.append(ImageTk.PhotoImage(image=Image.fromarray(img)))

	return npimages, photoimages_xy, photoimages_xz, photoimages_yz

def apply_contrast(npslice, f):
	minval = np.percentile(npslice, f) # vary threshold between 1st and 99th percentiles, when f=1
	maxval = np.percentile(npslice, 100-f)
	result = np.clip(npslice, minval, maxval)
	result = ((result - minval) / (maxval - minval)) * 255
	return result.astype(np.uint8)


def apply_brightness(npslice, f):
	bf = (26-f)/10
	return npslice/bf


def alert_popup(title, message, path):
    root = Toplevel()
    root.title(title)
    w = 400
    h = 100
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w)/2
    y = (sh - h)/2
    root.geometry('%dx%d+%d+%d' % (w, h, x, y))
    m = message
    m += '\n'
    m += path
    w = Label(root, text=m, width=120, height=10)
    w.pack()
    b = Button(root, text="OK", command=root.destroy, width=10)
    b.pack()
    mainloop()
		

class Annotate(object):

	def __init__(self, filename, save_mode='RGBA'):

		self.root=Tk(className="3D Annotation Toolbox")
		self.border = 0
		self.bd_color = 'red'
		self.color = "#FF0000"
		self.root.title("3D Annotation Toolbox")
		self.root.geometry("840x600")
		self.root.configure(background='white')
		self.filename=filename
		self.save_mode = save_mode

		self.setup_ui()
		
		self.photoimages={}
		self.current_slide_annotations = []
		self.c = {}
		self.zscale = 1
		self.canvas_popup_open = False

		self.npimages, self.photoimages['xy'], self.photoimages['xz'], self.photoimages['yz'] = read_tiff(filename)

		self.w = self.photoimages['xy'][0].width()
		self.h = self.photoimages['xy'][0].height()
		self.d = self.npimages.shape[0]
		self.annot3D = AnnotationSpace3D(self.npimages, (self.d, self.w, self.h), self.color)

		self.c['xz'] = Canvas(self.root, bg='white', width=self.w, height=self.d,highlightbackground=self.bd_color, highlightcolor=self.bd_color, highlightthickness = self.border)
		self.c['xz'].place(x=230,y=30)

		self.c['yz'] = Canvas(self.root, bg='white', width=self.d, height=self.h,highlightbackground=self.bd_color, highlightcolor=self.bd_color,highlightthickness = self.border,relief='ridge')
		self.c['yz'].place(x=190,y=70)

		self.c['xy'] = Canvas(self.root, bg='white', width=self.w, height=self.h,highlightbackground=self.bd_color, highlightcolor=self.bd_color, highlightthickness=self.border, relief='ridge')
		self.c['xy'].place(x=230,y=70)

		self.c['xz'].create_image(0, 0, image = self.photoimages['xz'][0], anchor = NW)
		self.c['yz'].create_image(0, 0, image = self.photoimages['yz'][0], anchor = NW)
		self.c['xy'].create_image(0, 0, image = self.photoimages['xy'][0], anchor = NW)

		self.c['xy'].configure(highlightthickness=2)
		self.c['xy'].update()

		
		self.c['xy'].create_image(0, 0, image = self.get_photo_slice('xy', 0), anchor = NW) # itemconfig(1, image=self.im)
		self.c['xz'].create_image(0, 0, image = self.get_photo_slice('xz', 0), anchor = NW) # itemconfig(1, image=self.im)
		self.c['yz'].create_image(0, 0, image = self.get_photo_slice('yz', 0), anchor = NW) # itemconfig(1, image=self.im)

		self.p = 'xy' # xy initially, yz, xz

		self.plane_data = {
			'xy': {'w': self.w, 'h': self.h, 'd': self.d},
			'xz': {'w': self.d, 'h': self.h, 'd': self.w},
			'yz': {'w': self.w, 'h': self.d, 'd': self.h}
		}

		self.main_w, self.main_h = self.plane_data[self.p]['w'], self.plane_data[self.p]['h']

		self.num_slides = self.plane_data[self.p]['d']

		self.slide_annotations = {
			'xy': [[] for i in range(self.d)], 
			'xz': [[] for i in range(self.w)], 
			'yz': [[] for i in range(self.h)]
		}

		self.current_spline = [] # list of line IDs created for that spline 

		self.root.bind("<Left>", self.slide_left)
		self.root.bind("<Right>", self.slide_right)
		self.root.bind('<Control-z>', self.undo)
		self.root.bind('<Control-s>', self.save_image)
		self.root.bind('r', lambda x:self.annot3D.plot3D())
		self.root.bind('b', lambda x:self.use_brush())
		self.root.bind('e', lambda x:self.use_eraser())
		self.root.bind('f', lambda x:self.canvas_popup())
		self.root.bind('1', lambda x:self.switch_plane('xy'))
		self.root.bind('2', lambda x:self.switch_plane('xz'))
		self.root.bind('3', lambda x:self.switch_plane('yz'))

		self.old_x = None
		self.old_y = None
		self.zoom_offsets = []
		self.line_width = self.choose_size_scale.get()
		self.eraser_on = False
		self.eraser_size=1 
		self.active_button = self.brush_button
		self.active_button.config(relief=SUNKEN)

		self.change_filter('cb', [self.choose_contrast_scale.get(), self.choose_brightness_scale.get()])
		self.change_gfilter('cb', [self.gchoose_contrast_scale.get(), self.gchoose_brightness_scale.get()])
		
		self.bind_controls_to_canvas(self.p)

		try:
			self.root.mainloop()
		except KeyboardInterrupt:
			exit(1)

	def setup_ui(self):
		#Creating the widgets 
		self.color_frame=LabelFrame(self.root, text='COLOR',bg="white", relief=RIDGE)
		self.color_frame.place(x=15,y=30,width=90,height=80)
		self.colors=["#FF0000","#0000FF", "#FFFF00", "#00FF00"]
		self.color_rgba = {"#FF0000" :[255, 0, 0, 255], "#0000FF" : [0, 0, 255, 255], "#FFFF00" :[255, 255, 0, 255], "#00FF00": [0, 255, 0, 255]}
		self.color_button = {}

		i=j=0
		for color in self.colors:
			if j==2:
				i+=1
				j=0
			self.color_button[color] = Button(self.color_frame, bg=color,bd=1, width=2, height=1, command=lambda col=color:self.select_color(col))
			self.color_button[color].grid(row=i,column=j)
			j+=1
		
		self.color_button[self.color].config(relief=SUNKEN)

		
		self.slide_text=LabelFrame(self.root,text="SLIDE", bg='white', relief=RIDGE) 
		self.slide_text.place(x=160,y=20,height=50, width=70)

		self.current_slide = {'xy': 0, 'xz': 0, 'yz': 0}

		self.current_slide_text = StringVar()
		self.current_slide_text.set('xy: 1')

		self.slide_label = Label(self.slide_text, bg="white",padx=10,textvariable=self.current_slide_text)
		self.slide_label.grid(row=0, column=5)

		
		img=Image.open(path.join("Icons","Brush.jpg"))
		img = img.resize((22,22), Image.ANTIALIAS)
		self.logo_icon = ImageTk.PhotoImage(img)
		
		img=Image.open(path.join("Icons","eraser.jpg"))
		img = img.resize((26,26), Image.ANTIALIAS)
		self.eraser_icon = ImageTk.PhotoImage(img)

		img=Image.open(path.join("Icons","Delete.png"))
		img = img.resize((26,26), Image.ANTIALIAS)
		self.delete_icon = ImageTk.PhotoImage(img)

		img=Image.open(path.join("Icons","save.png"))
		img = img.resize((18,18), Image.ANTIALIAS)
		self.save_icon = ImageTk.PhotoImage(img)

		img=Image.open(path.join("Icons","load.png"))
		img = img.resize((20,18), Image.ANTIALIAS)
		self.load_icon = ImageTk.PhotoImage(img)

		img=Image.open(path.join("Icons","merge.png"))
		img = img.resize((20,20), Image.ANTIALIAS)
		self.merge_icon = ImageTk.PhotoImage(img)

		img=Image.open(path.join("Icons","render.png"))
		img = img.resize((26,26), Image.ANTIALIAS)
		self.render_icon = ImageTk.PhotoImage(img)

		img = PhotoImage("photo", file=path.join("Icons","logo.gif"))
		self.root.tk.call('wm', 'iconphoto', self.root._w, img)

		self.load_image = Button(self.root ,image= self.load_icon,bg='white', height=28, width=28,relief=RIDGE, command=self.load_image)
		self.load_image.place(x=25,y=115)

		self.save_button = Button(self.root ,image= self.save_icon,bg='white', height=28, width=28,relief=RIDGE, command=self.save_image)
		self.save_button.place(x=60,y=115)

		self.merge_button = Button(self.root ,image = self.merge_icon,bg='white', height=28, width=28,relief=RIDGE, command=self.merge)
		self.merge_button.place(x=95,y=115)

		self.brush_button = Button(self.root,image= self.logo_icon, bg='white', height=28, width=28,relief=RIDGE,command=self.use_brush) 
		self.brush_button.place(x=25,y=150)

		self.eraser_button = Button(self.root,image= self.eraser_icon,bg='white', height=28, width=28,relief=RIDGE,command=self.use_eraser)
		self.eraser_button.place(x=60,y=150)

		self.clear_button = Button(self.root, image= self.delete_icon, bg='white', height=28, width=28,relief=RIDGE,command=self.clear)
		self.clear_button.place(x=25,y=185)

		self.render_button = Button(self.root ,image= self.render_icon,bg='white', height=28, width=28,relief=RIDGE, command=self.render_volume)
		self.render_button.place(x=60,y=185)

		

		y=225
		c=60

		self.size_text=LabelFrame(self.root,text="BRUSH SIZE", bg='white', relief=RIDGE)
		self.size_text.place(x=15,y=y,height=50, width=95)
		self.choose_size_scale=Scale(self.size_text, orient=HORIZONTAL, from_=1, to=15,length=85, width=10,sliderlength=10,bg="white")
		self.choose_size_scale.set(1)
		self.choose_size_scale.grid(row=0, column=0)

		self.size_text2=LabelFrame(self.root,text="ERASER SIZE", bg='white', relief=RIDGE)
		self.size_text2.place(x=15,y=y+c,height=50, width=95)
		self.choose_size_scale2=Scale(self.size_text2, orient=HORIZONTAL, from_=5, to=15,length=85, width=10,sliderlength=10,bg="white",command=self.get_val)
		self.choose_size_scale2.set(1)
		self.choose_size_scale2.grid(row=0, column=0)

		
		self.brightness_text=LabelFrame(self.root,text="BRIGHTNESS", bg='white', relief=RIDGE)
		self.brightness_text.place(x=15,y=y+(2*c),height=50, width=95)
		self.choose_brightness_scale=Scale(self.brightness_text, orient=HORIZONTAL, from_=5, to=25,length=85, width=10,sliderlength=10,bg="white", command=lambda f:self.change_filter('b', f))
		self.choose_brightness_scale.set(5)
		self.choose_brightness_scale.grid(row=5, column=0)

		
		self.contrast_text=LabelFrame(self.root,text="CONTRAST", bg='white', relief=RIDGE)
		self.contrast_text.place(x=15,y=y+(3*c),height=50, width=95)
		self.choose_contrast_scale=Scale(self.contrast_text, orient=HORIZONTAL, from_=1, to=40,length=85, width=10,sliderlength=10,bg="white", command=lambda f:self.change_filter('c', f))
		self.choose_contrast_scale.set(1)
		self.choose_contrast_scale.grid(row=5, column=0)
		
		
		self.gbrightness_text=LabelFrame(self.root,text="G BRIGHTNESS", bg='white', relief=RIDGE)
		self.gbrightness_text.place(x=15,y=y+(4*c),height=50, width=95)
		self.gchoose_brightness_scale=Scale(self.gbrightness_text, orient=HORIZONTAL, from_=5, to=25,length=85, width=10,sliderlength=10,bg="white", command=lambda f:self.change_gfilter('b', f))
		self.gchoose_brightness_scale.set(5)
		self.gchoose_brightness_scale.grid(row=5, column=0)

		
		self.gcontrast_text=LabelFrame(self.root,text="G CONTRAST", bg='white', relief=RIDGE)
		self.gcontrast_text.place(x=15,y=y+(5*c),height=50, width=95)
		self.gchoose_contrast_scale=Scale(self.gcontrast_text, orient=HORIZONTAL, from_=1, to=40,length=85, width=10,sliderlength=10,bg="white", command=lambda f:self.change_gfilter('c', f))
		self.gchoose_contrast_scale.set(1)
		self.gchoose_contrast_scale.grid(row=5, column=0)

		
	def switch_plane(self, plane):
		self.c[self.p].bind("<ButtonPress-1>", self.unbind)
		self.c[self.p].bind('<B1-Motion>', self.unbind)
		self.c[self.p].bind('<ButtonRelease-1>', self.unbind)
		self.c[self.p].bind("<ButtonPress-3>", self.unbind)
		self.c[self.p].bind("<B3-Motion>", self.unbind)
		self.c[self.p].bind("<MouseWheel>", self.unbind)
		self.c[self.p].bind("<Button-4>", self.unbind)
		self.c[self.p].bind("<Button-5>", self.unbind)

		if plane == 'xy':
			self.c['xy'].configure(highlightthickness=2)
			self.c['xz'].configure(highlightthickness=0)
			self.c['yz'].configure(highlightthickness=0)
			self.c['xy'].update()
			self.c['xz'].update()
			self.c['yz'].update()
		if plane == 'xz':
			self.c['xy'].configure(highlightthickness=0)
			self.c['xz'].configure(highlightthickness=2)
			self.c['yz'].configure(highlightthickness=0)
			self.c['xy'].update()
			self.c['xz'].update()
			self.c['yz'].update()
		if plane == 'yz':
			self.c['xy'].configure(highlightthickness=0)
			self.c['xz'].configure(highlightthickness=0)
			self.c['yz'].configure(highlightthickness=2)
			self.c['xy'].update()
			self.c['xz'].update()
			self.c['yz'].update()


		self.p = plane
		self.num_slides = self.plane_data[self.p]['d']
		self.current_slide_text.set(self.p + ': ' + str(self.current_slide[self.p]+1))
		self.main_w, self.main_h = self.plane_data[self.p]['h'], self.plane_data[self.p]['w']
		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 
		self.bind_controls_to_canvas(self.p)


	def unbind(self, event):
		pass


	def bind_controls_to_canvas(self, plane, except_zoom=False):
		self.c[plane].bind("<ButtonPress-1>", self.start_paint)
		self.c[plane].bind('<B1-Motion>', self.paint)
		self.c[plane].bind('<ButtonRelease-1>', self.reset)
		self.c[plane].bind("<ButtonPress-3>", self.move_start)
		self.c[plane].bind("<B3-Motion>", self.move_move)
		if not except_zoom:
			self.c[plane].bind("<MouseWheel>", lambda e: self.zoomM(e) if e.delta == -120 else self.zoomP(e)) # for windows
			self.c[plane].bind("<Button-4>", self.zoomP)
			self.c[plane].bind("<Button-5>", self.zoomM)


	def canvas_popup_on_closing(self):
		self.canvas_popup_open = False
		self.tl.destroy()
		self.c[self.p] = self.temp_canvas
		self.bind_controls_to_canvas(self.p)
		self.c[self.p].scale("all", 0, 0, 1/2, 1/2)
		self.zscale = 1
		self.zoom(1)
		self.c[self.p].config(width=self.main_w, height=self.main_h)
		self.change_slide(0)


	def canvas_popup(self):
		self.canvas_popup_open = True
		self.tl = Toplevel()
		self.tl.title(self.p)
		self.tl.bind("<Left>", self.slide_left)
		self.tl.bind("<Right>", self.slide_right)
		self.tl.bind('<Control-z>', self.undo)
		self.tl.bind('<Control-s>', self.save_image)
		self.tl.bind('r', lambda x:self.annot3D.plot3D())
		self.tl.bind('b', lambda x:self.use_brush())
		self.tl.bind('e', lambda x:self.use_eraser())

		self.c[self.p].bind("<ButtonPress-1>", self.unbind)
		self.c[self.p].bind('<B1-Motion>', self.unbind)
		self.c[self.p].bind('<ButtonRelease-1>', self.unbind)
		self.c[self.p].bind("<ButtonPress-3>", self.unbind)
		self.c[self.p].bind("<B3-Motion>", self.unbind)
		self.c[self.p].bind("<MouseWheel>", self.unbind)
		self.c[self.p].bind("<Button-4>", self.unbind)
		self.c[self.p].bind("<Button-5>", self.unbind)

		self.temp_canvas = self.c[self.p]
		self.c[self.p] = Canvas(self.tl, bg='white', width=self.main_w, height=self.main_h)
		self.c[self.p].pack()

		self.bind_controls_to_canvas(self.p, except_zoom=True)

		self.c[self.p].create_image(0, 0, image = self.photoimages[self.p][0], anchor = NW)
		self.c[self.p].create_image(0, 0, image = self.get_photo_slice(self.p, 0), anchor = NW)

		self.c[self.p].config(width=self.main_w*2, height=self.main_h*2)

		self.zscale = 2
		self.zoom(2)

		self.tl.protocol("WM_DELETE_WINDOW", self.canvas_popup_on_closing)
		self.tl.mainloop()


	def get_photo_slice(self, p, d):
		self.s = self.annot3D.get_slice(p, d)
		self.im = ImageTk.PhotoImage(image=Image.fromarray(self.s))
		return self.im
		
	def use_brush(self):
		self.activate_button(self.brush_button)


	def clear(self):
		self.annot3D.clear_slice(self.p, self.current_slide[self.p])
		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 


	def get_val(self, val): 
		self.eraser_size=val 


	def select_color(self,col):
		self.color=col
		for c in self.colors:
			self.color_button[c].config(relief=RAISED)
		
		self.color_button[col].config(relief=SUNKEN)
		self.activate_button(self.brush_button)


	def slide_left(self, event):
		if (self.current_slide[self.p] > 0):
			self.change_slide(-1)


	def slide_right(self, event):
		if (self.current_slide[self.p] < self.num_slides-1):
			self.change_slide(1)


	def change_slide(self, step):
		self.current_slide[self.p] += step
		self.current_slide_text.set(self.p + ': ' + str(self.current_slide[self.p]+1))

		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 

		self.change_filter('cb', [self.choose_contrast_scale.get(), self.choose_brightness_scale.get()])
		self.change_gfilter('cb', [self.gchoose_contrast_scale.get(), self.gchoose_brightness_scale.get()])

		if self.canvas_popup_open: # keep zoomed in
			self.zoom(2)


	def move_start(self, event):
		self.c[self.p].scan_mark(event.x, event.y)

	def move_move(self, event):
		self.c[self.p].scan_dragto(event.x, event.y, gain=1)


	def zoom(self, zscale):
		self.zoomres = self.photoimages[self.p][self.current_slide[self.p]]._PhotoImage__photo.zoom(zscale,zscale)
		self.c[self.p].itemconfig(1, image=self.zoomres)

		self.zoomres2 = self.get_photo_slice(self.p, self.current_slide[self.p])._PhotoImage__photo.zoom(zscale,zscale)
		self.c[self.p].itemconfig(2, image=self.zoomres2)

		self.c[self.p].configure(scrollregion = self.c[self.p].bbox("all"))


	def zoomP(self,event): 
		if self.zscale != 2:
			self.zscale += 1

			offx = (event.x/(self.main_w*self.zscale))
			offy = (event.y/(self.main_h*self.zscale))

			# self.c[self.p].scale("all", 0, 0, self.zscale, self.zscale)
			self.zoom(self.zscale)

			self.c[self.p].xview_moveto(offx)
			self.c[self.p].yview_moveto(offy)

			if self.zscale == 2: # going into 2
				self.zoom_offsets.append((offx,offy))


	def zoomM(self,event):
		if self.zscale != 1:
			self.c[self.p].scale("all", 0, 0, 1/self.zscale, 1/self.zscale)
			self.zscale -= 1
			
			self.zoom(self.zscale)

			if self.zscale == 2: # going back to 2
				offx, offy = self.zoom_offsets[-1] # previous zoom

				self.c[self.p].xview_moveto(offx)
				self.c[self.p].yview_moveto(offy)



	def change_filter(self, filter, val):
		fc = 0
		fb = 0
		np_slice = None

		if filter == 'cb':
			fc = int(val[0])
			fb = int(val[1])
		elif filter =='c':
			fc = int(val)
			fb = int(self.choose_brightness_scale.get())
		else:
			fb = int(val)
			fc = int(self.choose_contrast_scale.get())

		np_slice = None
		cs = self.current_slide[self.p]
		
		if (self.p == 'xy'):
			np_slice =self.npimages[cs]
		elif (self.p == 'xz'):
			np_slice = np.swapaxes(self.npimages, 0, 1)[cs]
		elif (self.p == 'yz'):
			np_slice = np.swapaxes(self.npimages, 0, 2)[cs]

		np_slice = apply_contrast(np_slice, fc)
		np_slice = apply_brightness(np_slice, fb)

		self.photoimages[self.p][self.current_slide[self.p]] = ImageTk.PhotoImage(image=Image.fromarray(np_slice))
		self.c[self.p].itemconfig(1, image=self.photoimages[self.p][self.current_slide[self.p]])

	
	def change_gfilter(self, filter, val):
		fc = 0
		fb = 0
		np_slice = None

		if filter == 'cb':
			fc = int(val[0])
			fb = int(val[1])
		elif filter =='c':
			fc = int(val)
			fb = int(self.choose_brightness_scale.get())
		else:
			fb = int(val)
			fc = int(self.choose_contrast_scale.get())


		for ax in ['xy','xz','yz']:
			# new np slices produced from filter effects
			np_slice = None
			cs = self.current_slide[ax]
			
			if (ax == 'xy'):
				np_slice =self.npimages[cs]
			elif (ax == 'xz'):
				np_slice = np.swapaxes(self.npimages, 0, 1)[cs]
			elif (ax == 'yz'):
				np_slice = np.swapaxes(self.npimages, 0, 2)[cs]

			np_slice = apply_contrast(np_slice, fc)
			np_slice = apply_brightness(np_slice, fb)

			self.photoimages[ax][self.current_slide[ax]] = ImageTk.PhotoImage(image=Image.fromarray(np_slice))
			self.c[ax].itemconfig(1, image=self.photoimages[ax][self.current_slide[ax]])


	def use_eraser(self):
		self.activate_button(self.eraser_button, eraser_mode=True)

	def render_volume(self):
		self.annot3D.plot3D()

	def load_image(self, event=None):	
		load_file = askopenfile(mode='r').name
		self.annot3D.load(load_file)
		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 

	def merge(self,event=None):
		files = askopenfilenames(parent=self.root,title='Choose atleast two files to merge')
		path_list = self.root.tk.splitlist(files)
		self.annot3D.mergeload(path_list)
		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 
		

	def save_image(self, event=None):
		self.activate_button(self.save_button, eraser_mode=False)

		save_file = asksaveasfile(mode='wb').name
		print("Now writing save file as %s..." % save_file)

		self.annot3D.save(save_file)
		print("Saved!")

		alert_popup("Saved!", "Your annotation data was saved at:", save_file)

		

	def activate_button(self, some_button, eraser_mode=False):
		self.active_button.config(relief=RAISED) # previous button raised up
		some_button.config(relief=SUNKEN) # current active button pressed down
		self.active_button = some_button
		self.eraser_on = eraser_mode


	def undo(self, event):
		self.annot3D.undo_history()
		self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 


	def start_paint(self, event): # when painting starts (click)
		self.annot3D.save_history(self.p, self.current_slide[self.p]) # save history after every line stroke


	def paint(self, event): 
		d = self.current_slide[self.p]
		x, y = event.x-1, event.y-1
		px, py = event.x, event.y
		bs = self.choose_size_scale.get()
		es = self.choose_size_scale2.get()

		w = int(self.c[self.p].canvasx(px)) # relative to absolute
		h = int(self.c[self.p].canvasy(py))
		
		if self.zscale != 1:
			w /= self.zscale
			h /= self.zscale

		if (self.eraser_on): 
			self.annot3D.draw(self.p, d, w, h, es, 0,[0,0,0,0])
		else:
			# if self.old_x and self.old_y:
			self.annot3D.draw(self.p, d, w, h, bs, 1,self.color_rgba[self.color])
			self.current_spline.append((w, h))

		if self.zscale == 1:
			self.c[self.p].itemconfig(2, image = self.get_photo_slice(self.p, self.current_slide[self.p])) 
		else:
			self.im = self.get_photo_slice(self.p, self.current_slide[self.p])._PhotoImage__photo.zoom(self.zscale, self.zscale)
			self.c[self.p].itemconfig(2, image = self.im) 
			
		self.old_x = event.x
		self.old_y = event.y


	def reset(self, event): # brush/eraser mouse b1 released
		self.old_x, self.old_y = None, None

		self.current_slide_annotations.append(self.current_spline)

		self.current_spline = [] # reset
		self.save_fill = []


if __name__ == '__main__':
	try:
		Annotate(sys.argv[1], sys.argv[2])
	except KeyboardInterrupt:
		exit(1)