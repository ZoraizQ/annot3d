import numpy as np
import pickle
import imageio
from multiprocessing import Process
from PIL import Image
import matplotlib.pyplot as plt
import os 
import models
from tqdm import tqdm
from helpers import disk
import asyncio

target_size_init = (32, 640)

def normalize(img): # normalized between 1 and -1
    min = img.min()
    max = img.max()
    x = 2.0 * (img - min) / (max - min) - 1.0
    return x

class AnnotationSpace3D():
	
	def __init__(self, npimages, dimensions, color_rgba):
		self.npimages = npimages
		self.npspace_rgba = np.zeros((dimensions[0], dimensions[1], dimensions[2], 4), np.uint8)
		self.npspace = np.zeros(dimensions, dtype=np.uint8)
		self.dim = dimensions # 25,500,500
		self.MAX_UNDOS = 10
		self.undo_stack = [] # state history undo type, tuples (plane, npspace slice, npspace rgba slice) (slice of voxels) FOR ALL PLANES
		self.color_rgba = color_rgba
		self.server_url = ''
		self.predict_mode = 'local'
		self.model = None
		self.connection_context = None
		self.socket = None

	def get_npimages(self):
		return self.npimages

	def get_npspace(self):
		return self.npspace

	def draw(self, plane, curr_slide, x, y, brush_size, is_brush, color_rgba):
		if plane == 'xy':
			rr, cc = disk(center=(y, x), radius=brush_size, shape=(self.dim[1], self.dim[2]))
			self.npspace[curr_slide, rr, cc] = is_brush
			self.npspace_rgba[curr_slide, rr, cc] = color_rgba


		elif plane == 'yz':
			rr, cc = disk(center=(y, x), radius=brush_size, shape=(self.dim[1], self.dim[0]))
			self.npspace[:,:,curr_slide][cc, rr] = is_brush
			self.npspace_rgba[:,:,curr_slide][cc, rr] = color_rgba
			

		elif plane == 'xz':
			rr, cc = disk(center=(y, x) , radius=brush_size, shape=(self.dim[0], self.dim[1]))
			self.npspace[:,curr_slide,:][rr, cc] = is_brush
			self.npspace_rgba[:,curr_slide,:][rr, cc] = color_rgba


	def save(self, path):
		file = open(path, 'wb')
		pickle.dump(self.npspace_rgba, file)
		file.close()
		imageio.mimwrite(path+'.tiff', self.npspace_rgba)
		

	def exportProcess(self, path, plane):
		os.mkdir(path) 
		image_path = os.path.join(path, 'image')
		label_path = os.path.join(path, 'label')
		os.mkdir(image_path)
		os.mkdir(label_path) 

		pindex = 0 # xy
		if plane == 'xz':
			pindex = 1
		elif plane == 'yz':
			pindex = 2
		
		for i in range(self.npimages.shape[pindex]):
			fname = str(i)+'.png'
			im = np.array([])
			if plane == 'xy':
				im = self.npimages[i]
			elif plane == 'xz':
				im = self.npimages[:,i,:]
			elif plane == 'yz':
				im = self.npimages[:,:,i]
				
			imageio.imwrite(uri=os.path.join(image_path, fname), im=im, format='PNG-PIL')  
		
		# 1 -> 0 black, 0 -> 255 white for 3D annotation matrix
		self.npspace8bit = np.where(self.npspace==0, 255, self.npspace)
		self.npspace8bit = np.where(self.npspace8bit==1, 0,self.npspace8bit)

		for i in range(self.npimages.shape[pindex]):
			fname = str(i)+'.png'
			im = np.array([])
			if plane == 'xy':
				im = self.npspace8bit[i]
			elif plane == 'xz':
				im = self.npspace8bit[:,i,:]
			elif plane == 'yz':
				im = self.npspace8bit[:,:,i]

			label_img = Image.fromarray(im.astype(np.uint8))
			label_img.save(os.path.join(label_path, fname), "PNG")
		
		print("Exported to", path)


	def export(self, path, plane): 
		exportproc = Process(target=self.exportProcess, args=(path, plane,)) # parallel
		exportproc.start()
		

	def load_model_weights(self, model_weights_file): # hdf5 file
		''' load model weights for unet from given file and input size for xz default '''
		self.model = models.unet(pretrained_weights=model_weights_file, input_size=(32, 640, 1))
		self.model.summary()
		print("Model loaded successfully.")
		

	def set_server_url(self, url):
		self.server_url = url
		self.predict_mode = 'server'


	def model_predict(self, p, cs):
		img = self.get_src_slice(p, cs)
		print("Predicting for", p, cs+1,"from",self.predict_mode)

		if self.predict_mode == 'server':
			import requests
			import json
			
			url = self.server_url
			api = "/predict_model"
			url += api

			data = {'slide': img.tolist()}

			response = requests.post(url, json=data)
			print(response)

			if response.status_code == 200:
				bin_pred = json.loads(response.content)['prediction']
				bin_pred = np.array(bin_pred)
				print(bin_pred.shape)

				rgba_pred = np.stack((bin_pred,)*4, axis=-1)
				rgba_pred = np.where(rgba_pred == [1,1,1,1], self.color_rgba, [0,0,0,0]) #color for rgba else transparent

				if p == 'xy':
					self.npspace[cs] = bin_pred
					self.npspace_rgba[cs] = rgba_pred
				elif p == 'yz':
					self.npspace[:,:,cs] = bin_pred
					self.npspace_rgba[:,:,cs] = rgba_pred
				elif p == 'xz':
					self.npspace[:,cs,:] = bin_pred
					self.npspace_rgba[:,cs,:] = rgba_pred
			else:
				print('Predict API call failed.', response)


		elif self.predict_mode == 'local':

			if (self.model is None): # model has not been loaded
				print("No model loaded for local predictions.")
				return

			try:
				from tensorflow import image as tfimage

				img = normalize(img)
				img = np.reshape(img,img.shape+(1,))
				img = tfimage.pad_to_bounding_box(img, 0, 0, target_size_init[0], target_size_init[1])
				img = np.reshape(img,(1,)+img.shape) # (x,y,1) -> (1,x,y,1)

				np_results = self.model.predict(img, verbose=1)
				pred = np_results[0]
				# output = pred[:,:,0]*255
				pred = pred.reshape(pred.shape[0], pred.shape[1])
				# print("prediction", pred.shape, np.max(pred), np.min(pred))
				# print("prediction out", output.shape, np.max(output), np.min(output))
				# plt.figure()
				# plt.imshow(output)
				# plt.show()

				t = 0.8 # thresholding param

				bin_pred = np.copy(pred)
				bin_pred = np.where(bin_pred < t, 1, 0) # transparent if above threshold else annotation
				bin_pred = bin_pred[:25, :500]

				rgba_pred = np.stack((bin_pred,)*4, axis=-1)
				rgba_pred = np.where(rgba_pred == [1,1,1,1], [255,0,0,255], [0,0,0,0]) #color for rgba else transparent

				if p == 'xy':
					self.npspace[cs] = bin_pred
					self.npspace_rgba[cs] = rgba_pred
				elif p == 'yz':
					self.npspace[:,:,cs] = bin_pred
					self.npspace_rgba[:,:,cs] = rgba_pred
				elif p == 'xz':
					# print(bin_pred.dtype, self.npspace[:,cs,:].dtype, self.npspace.dtype)
					self.npspace[:,cs,:] = bin_pred
					self.npspace_rgba[:,cs,:] = rgba_pred
					# print(bin_pred.dtype, self.npspace[:,cs,:].dtype, self.npspace.dtype)

			except Exception as e:
				print(e)
			

	def load(self, path):
		file = open(path, 'rb')
		self.npspace_rgba = pickle.load(file)
		file.close()
		self.npspace = np.clip(np.sum(self.npspace_rgba, axis=3), 0, 1) # e.g. [0,0,255,255] sums to 510 then clipped to 1

		# import mcubes
		# vertices, triangles = mcubes.marching_cubes(self.npspace, 0)
		# mcubes.export_obj(vertices, triangles, 'annot.obj')

	def mergeload(self, path_list):
		self.npspace_rgba = np.zeros((self.dim[0], self.dim[1], self.dim[2], 4), np.uint8)
		for path in path_list:
			file = open(path, 'rb')
			self.npspace_rgba += pickle.load(file)
			file.close()

		self.npspace_rgba = np.clip(self.npspace_rgba, 0, 255)
		self.npspace = np.clip(np.sum(self.npspace_rgba, axis=3), 0, 1)


	def save_history(self, plane, curr_slide):
		if (len(self.undo_stack) == self.MAX_UNDOS): # when max undos reached
			self.undo_stack.pop(0) # head removed, to make room for more at tail
		
		npspace_slice, npspace_rgba_slice = None, None
		# before modifying original save history of slices
		if plane == 'xy':
			npspace_slice, npspace_rgba_slice = self.npspace[curr_slide], self.npspace_rgba[curr_slide]
		elif plane == 'yz':
			npspace_slice, npspace_rgba_slice = self.npspace[:,:,curr_slide], self.npspace_rgba[:,:,curr_slide]
		elif plane == 'xz':
			npspace_slice, npspace_rgba_slice = self.npspace[:,curr_slide,:], self.npspace_rgba[:,curr_slide,:]

		self.undo_stack.append((plane, curr_slide, np.copy(npspace_slice), np.copy(npspace_rgba_slice)))


	def undo_history(self):
		if (len(self.undo_stack) != 0): # not empty
			plane, curr_slide, npspace_slice, npspace_rgba_slice = self.undo_stack.pop()
			if plane == 'xy':
				self.npspace[curr_slide] = npspace_slice
				self.npspace_rgba[curr_slide] = npspace_rgba_slice

			elif plane == 'yz':
				self.npspace[:,:,curr_slide] = npspace_slice
				self.npspace_rgba[:,:,curr_slide] = npspace_rgba_slice

			elif plane == 'xz':
				self.npspace[:,curr_slide,:] = npspace_slice
				self.npspace_rgba[:,curr_slide,:] = npspace_rgba_slice


	def get_npspace(self):
		return self.npspace


	def get_slice(self, p, cs):
		if p == 'xy':
			return self.npspace_rgba[cs]
		elif p == 'xz':
			return self.npspace_rgba[:,cs,:]
		elif p == 'yz':
			return np.swapaxes(self.npspace_rgba, 0, 2)[cs]

	def get_src_slice(self, p, cs):
		if p == 'xy':
			return self.npimages[cs]
		elif p == 'xz':
			return self.npimages[:,cs,:]
		elif p == 'yz':
			return np.swapaxes(self.npimages, 0, 2)[cs]


	def clear_slice(self, p, cs):
		w,h,d = self.dim
		if p == 'xy':
			self.npspace[cs] = np.zeros((h, d), np.uint8)
			self.npspace_rgba[cs] = np.zeros((h, d, 4), np.uint8)
		elif p == 'yz':
			self.npspace[:,:,cs] = np.zeros((h, w), np.uint8)
			self.npspace_rgba[:,:,cs] = np.zeros((h, w, 4), np.uint8)
		elif p == 'xz':
			self.npspace[:,cs,:] = np.zeros((w, h), np.uint8)
			self.npspace_rgba[:,cs,:] = np.zeros((w, h, 4), np.uint8)

	
