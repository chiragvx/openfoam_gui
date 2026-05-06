import vtk

class AircraftCameraStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self):
        super().__init__()
        self._ctrl_locked = False
        self._snap_callback = None
        self.AddObserver("RightButtonPressEvent",   self._right_press)
        self.AddObserver("RightButtonReleaseEvent", self._right_release)
        self.AddObserver("KeyPressEvent",           self._key_press)
        self.AddObserver("KeyReleaseEvent",         self._key_release)
        self.AddObserver("LeftButtonPressEvent",    self._left_press)

    def _right_press(self, obj, event):
        self.StartPan()          # pan instead of zoom on right-click

    def _right_release(self, obj, event):
        self.EndPan()

    def _key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key in ("Control_L", "Control_R", "ctrl"):
            self._ctrl_locked = True
            # snap camera to nearest axis — call back via stored plotter ref
            if self._snap_callback:
                self._snap_callback()

    def _key_release(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key in ("Control_L", "Control_R", "ctrl"):
            self._ctrl_locked = False

    def _left_press(self, obj, event):
        if self._ctrl_locked:
            self.StartPan()      # pan-only while Ctrl held
        else:
            self.OnLeftButtonDown()  # normal rotate

    # Attach a callback so ViewportWidget can snap camera on Ctrl press
    def set_snap_callback(self, cb):
        self._snap_callback = cb
