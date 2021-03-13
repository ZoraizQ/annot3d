from mayavi import mlab
import pyvista as pv
import numpy as np
import zmq

class Plot3D():
	
    def __init__(self, npimages=None, npspace=None):
        self.npimages = npimages
        self.npspace = npspace
		
    def plotPyvistaUniformGrid(self):
        grid = pv.UniformGrid()
        grid.dimensions = self.npimages.shape
        grid.origin = (100, 33, 55.6)  # The bottom left corner of the data set
        grid.spacing = (1, 1, 1)  # These are the cell sizes along each axis
        bgimage = self.npimages.flatten(order="F") # flatten
        segmask = self.npspace.flatten(order="F")
        grid.point_arrays["values"] = np.where(segmask == 0, bgimage, segmask)
        grid.plot(text="3D Visualization - UniformGrid", window_size=[400,400])

    def plotPyvistaVolume(self):
        bgimage = pv.wrap(self.npimages)
        segmask = pv.wrap(self.npspace)
        p = pv.Plotter()
        p.add_volume(bgimage, cmap="viridis")
        p.add_volume(segmask, cmap="coolwarm")
        p.link_views()
        p.show()

    def plotMayaviVolume(self):
        mlab.figure(figure='3D Visualization')
        bg_original = mlab.pipeline.volume(mlab.pipeline.scalar_field(self.npimages))
        segmask = mlab.pipeline.iso_surface(mlab.pipeline.scalar_field(self.npspace), color=(1.0, 0.0, 0.0))
        mlab.show()

    def plot3D(self):
        self.plotMayaviVolume()
        # self.plotPyvistaUniformGrid()
        # self.plotPyvistaVolume()
    
    def run(self):
        self.npimages = np.load('npimages.npy')

        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.bind("tcp://*:5555")

        while True:
            print("Waiting for render request.")
            message = socket.recv()
            print("Received request: %s" % message)

            self.npspace = np.load('npspace.npy')
            self.plot3D()

            socket.send(b'Rendered.')

          
if __name__ == '__main__':
    Plot3D().run()