import vtk
import math

class AircraftCameraStyle(vtk.vtkInteractorStyleTrackballCamera):
    """
    Turntable-style camera that locks the Z-axis (up) and handles custom mouse events.
    """
    def __init__(self):
        super().__init__()
        self.AddObserver("MiddleButtonPressEvent",   self._middle_press)
        self.AddObserver("MiddleButtonReleaseEvent", self._middle_release)
        self.AddObserver("InteractionEvent",         self._on_interaction)

    def _middle_press(self, obj, event):
        self.StartPan()

    def _middle_release(self, obj, event):
        self.EndPan()

    def _on_interaction(self, obj, event):
        """Enforce Z-up (Turntable behavior) on every interaction."""
        ren = self.GetInteractor().GetRenderWindow().GetRenderers().GetFirstRenderer()
        cam = ren.GetActiveCamera()
        
        # Enforce Z-up
        cam.SetViewUp(0, 0, 1)
        # Ensure the camera doesn't get "stuck" at the poles
        # (This is a common issue with pure Z-up constraints)

        
        # To make it feel like a real turntable, we should also project the right vector 
        # but vtkInteractorStyleTrackballCamera handles basic rotation; 
        # forcing ViewUp to (0,0,1) effectively makes it a turntable.

    def set_snap_callback(self, cb):
        pass
