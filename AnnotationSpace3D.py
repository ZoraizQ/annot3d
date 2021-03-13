import numpy as np
from skimage import draw
from mayavi import mlab
import pickle
import imageio


class AnnotationSpace3D():
	def __init__(self, npimages, dimensions, color):
		self.npimages = npimages
		self.npspace_rgba = np.zeros((dimensions[0], dimensions[1], dimensions[2], 4), np.uint8)
		self.npspace = np.zeros(dimensions, dtype=np.uint8)
		self.dim = dimensions # 25,500,500
		self.MAX_UNDOS = 10
		self.undo_stack = [] # state history undo type, tuples (plane, npspace slice, npspace rgba slice) (slice of voxels) FOR ALL PLANES

		self.color = color




	def draw(self, plane, curr_slide, x, y, brush_size, is_brush, color_rgba):
		if plane == 'xy':
			rr, cc = draw.disk(center=(y, x), radius=brush_size, shape=(self.dim[1], self.dim[2]))
			self.npspace[curr_slide, rr, cc] = is_brush
			self.npspace_rgba[curr_slide, rr, cc] = color_rgba


		elif plane == 'yz':
			rr, cc = draw.disk(center=(y, x), radius=brush_size, shape=(self.dim[1], self.dim[0]))
			self.npspace[:,:,curr_slide][cc, rr] = is_brush
			self.npspace_rgba[:,:,curr_slide][cc, rr] = color_rgba
			

		elif plane == 'xz':
			rr, cc = draw.disk(center=(y, x) , radius=brush_size, shape=(self.dim[0], self.dim[1]))
			self.npspace[:,curr_slide,:][rr, cc] = is_brush
			self.npspace_rgba[:,curr_slide,:][rr, cc] = color_rgba

	def save(self, path):
		file = open(path, 'wb')
		pickle.dump(self.npspace_rgba, file)
		file.close()
		imageio.mimwrite(path+'.tiff', self.npspace_rgba)

	def load(self, path):
		file = open(path, 'rb')
		self.npspace_rgba = pickle.load(file)
		file.close()
		self.npspace = np.clip(np.sum(self.npspace_rgba, axis=3), 0, 1) # e.g. [0,0,255,255] sums to 510 then clipped to 1

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


	def plot3D(self):
		mlab.figure(figure='3D Visualization')
		bg_original = mlab.pipeline.volume(mlab.pipeline.scalar_field(self.npimages))
		segmask = mlab.pipeline.iso_surface(mlab.pipeline.scalar_field(self.npspace), color=(1.0, 0.0, 0.0))
		mlab.show()
		

	def get_npspace(self):
		return self.npspace


	def get_slice(self, p, cs):
		if p == 'xy':
			return self.npspace_rgba[cs]
		elif p == 'xz':
			return self.npspace_rgba[:,cs,:]
		elif p == 'yz':
			return np.swapaxes(self.npspace_rgba, 0, 2)[cs]


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

	
