#!/usr/bin/env python3
"""macOS click-through teacher overlay above REAL Autodesk Fusion Desktop.

This is the display half of the native exCADmple Fusion add-in. The learner
can edit with their own cursor; the expert cursor is a drawn pixel shape.
It reads sourced CAD operation events from core/playback/virtual_expert.py.

The overlay draws tool use and parameters in a native-app-like teaching
sequence. It does NOT create a second native Fusion dialog or replay actual
historic clicks (the .f3d does not contain that history).
"""
import argparse
import json
import sys
import time
from pathlib import Path

STATE_FILE = Path.home() / "Library" / "Application Support" / "exCADmple" / "expert_state.json"
CONFIG_FILE = Path.home() / "Library" / "Application Support" / "exCADmple" / "anchors.json"

try:
    from AppKit import (
        NSApplication, NSApplicationActivationPolicyAccessory,
        NSWindow, NSView, NSColor, NSBezierPath, NSString, NSFont, NSScreen,
        NSFontAttributeName, NSForegroundColorAttributeName, NSWorkspace,
        NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
        NSFloatingWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary)
    from Foundation import NSObject, NSTimer, NSMakeRect, NSMakePoint
except ImportError as error:
    print("Install PyObjC on macOS: python3 -m pip install pyobjc-framework-Cocoa", file=sys.stderr)
    raise

DEFAULT_ANCHORS = {
    "tool": [.20,.93],
    "reference": [.60,.46],
    "parameter": [.79,.65],
    "confirm": [.81,.48],
}


def _draw_text(text, x, y, font=13, color=None):
    color = color or NSColor.whiteColor()
    NSString.stringWithString(str(text)).drawAtPoint_withAttributes_(
        NSMakePoint(x,y), {
            NSFontAttributeName: NSFont.systemFontOfSize_(font),
            NSForegroundColorAttributeName: color,
        })


def _rounded(rect, color, radius=10):
    color.setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(*rect),radius,radius).fill()


def _line(x,y,x1,y1,color,width=2):
    color.setStroke()
    path = NSBezierPath.bezierPath()
    path.setLineWidth_(width)
    path.moveToPoint_(NSMakePoint(x,y))
    path.lineToPoint_(NSMakePoint(x1,y1))
    path.stroke()


class TeacherView(NSView):
    def initWithFrame_(self, frame):
        self=super().initWithFrame_(frame)
        if self is None:
            return None
        self.state = None
        self.anchors = DEFAULT_ANCHORS
        return self

    def drawRect_(self, rect):
        state = self.state
        if not state or not state.get("active"):
            return
        bounds = self.bounds()
        w, h = bounds.size.width, bounds.size.height
        anchors = self.anchors
        phase = int(state.get("phase",0))
        progress = max(0,min(1,float(state.get("progress",0))))
        # A small label at the bottom so the real CAD viewport stays clear.
        _rounded((25,38,min(650,w-50),66), NSColor.colorWithCalibratedRed_green_blue_alpha_(
            .055,.075,.095,.91))
        title = "%02d   %s" % (int(state.get("index",0))+1,state.get("step",""))
        _draw_text(title[:72],41,78,15)
        phases = ("Choose Fusion tool","Select reference geometry","Set command parameters","Confirm operation")
        _draw_text(phases[min(3,phase)],41,53,12,
                   NSColor.colorWithCalibratedRed_green_blue_alpha_(.95,.74,.36,1))
        reason = str(state.get("reason","")).strip()
        if reason and phase >= 2:
            _rounded((25,112,min(650,w-50),62),NSColor.colorWithCalibratedRed_green_blue_alpha_(
                .07,.1,.12,.93))
            _draw_text("WHY",41,149,11,
                       NSColor.colorWithCalibratedRed_green_blue_alpha_(.97,.70,.30,1))
            _draw_text(reason[:96],41,128,12)
        # Simulated CAD command input appears over the *actual application*,
        # but it is a visual explanation, NEVER a second active Fusion command.
        if phase >= 2:
            px,py = (anchors["parameter"][0]*w,anchors["parameter"][1]*h)
            pw = min(315,w*.32)
            _rounded((px-30,py-75,pw,144),
                     NSColor.colorWithCalibratedRed_green_blue_alpha_(.12,.14,.17,.94))
            _draw_text(str(state.get("tool","CAD operation"))[:34],px-15,py+37,15)
            params = state.get("parameters") or []
            if not params:
                params = ["Use the selected CAD operation"]
            for i,value in enumerate(params[:3]):
                _draw_text(str(value)[:42],px-15,py+9-i*25,12)
            if phase == 3:
                _rounded((px+pw-128,py-62,75,26),
                         NSColor.colorWithCalibratedRed_green_blue_alpha_(.18,.50,.63,1))
                _draw_text("OK",px+pw-106,py-55,12)
        stages = ["tool","reference","parameter","confirm"]
        point=[anchors[stage] for stage in stages]
        # Prefer the REAL reference feature's projected 3D center when Fusion
        # can resolve it. Coordinates from Viewport.viewToScreen use a
        # top-left screen origin, unlike Cocoa's bottom-left origin.
        focus=state.get("screen_anchor")
        if (isinstance(focus,list) and len(focus)==2
                and all(isinstance(v,(int,float)) for v in focus)):
            fx,fy=float(focus[0]),float(focus[1])
            if 0 <= fx <= w and 0 <= fy <= h:
                point[1]=[fx/w, 1-fy/h]
        # Actual OS cursor is untouched. This virtual pointer travels between
        # real Fusion UI regions while the user may work simultaneously.
        destination=point[min(3,phase)]
        previous=point[max(0,phase-1)] if phase else [.49,.57]
        u=(progress*4-phase)
        if phase == 3 and progress == 1:
            u=1.
        u=max(0,min(1,u))
        u=u*u*(3-2*u)
        x=(previous[0]*(1-u)+destination[0]*u)*w
        y=(previous[1]*(1-u)+destination[1]*u)*h
        gold=NSColor.colorWithCalibratedRed_green_blue_alpha_(1,.68,.18,1)
        # Draw a recognisable virtual cursor arrow and small teacher tag.
        _line(x,y,x+3,y-24,gold,3)
        _line(x,y,x+16,y-17,gold,2)
        _line(x+3,y-24,x+7,y-16,gold,2)
        _rounded((x+15,y-34,62,20),NSColor.colorWithCalibratedRed_green_blue_alpha_(
            .19,.20,.23,.95),5)
        _draw_text("EXPERT",x+20,y-29,10)
        if not state.get("playing"):
            _draw_text("PAUSED",w-112,40,12,
                       NSColor.colorWithCalibratedRed_green_blue_alpha_(.92,.65,.4,1))


class EventReader(NSObject):
    def initWithWindow_view_path_config_(self,window,view,path,config):
        self=super().init()
        if self is None:
            return None
        self.window=window
        self.view=view
        self.path=path
        self.config=config
        self.last_mtime=-1
        self.visible=False
        return self

    def tick_(self,timer):
        try:
            app=NSWorkspace.sharedWorkspace().frontmostApplication()
            name=str(app.localizedName()) if app else ""
            # Keep overlay behind non-CAD apps, especially Terminal.
            should_show="Fusion" in name
            if should_show and not self.visible:
                self.window.orderFrontRegardless()
                self.visible=True
            elif not should_show and self.visible:
                self.window.orderOut_(None)
                self.visible=False
            if self.path.exists():
                modified=self.path.stat().st_mtime_ns
                if modified != self.last_mtime:
                    self.last_mtime=modified
                    self.view.state=json.loads(self.path.read_text(encoding="utf-8"))
            if self.config.exists():
                # Configuration is tiny; reload to support live calibration.
                anchors=json.loads(self.config.read_text(encoding="utf-8"))
                if isinstance(anchors,dict) and all(k in anchors for k in DEFAULT_ANCHORS):
                    self.view.anchors=anchors
            if self.visible:
                self.view.setNeedsDisplay_(True)
        except Exception as err:
            print("Expert overlay:",err,file=sys.stderr)


def run(config, state):
    app=NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    frame=NSScreen.mainScreen().frame()
    window=NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame,NSWindowStyleMaskBorderless,NSBackingStoreBuffered,False)
    window.setOpaque_(False)
    window.setBackgroundColor_(NSColor.clearColor())
    window.setHasShadow_(False)
    window.setIgnoresMouseEvents_(True)
    window.setLevel_(NSFloatingWindowLevel)
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces |
        NSWindowCollectionBehaviorFullScreenAuxiliary)
    view=TeacherView.alloc().initWithFrame_(NSMakeRect(
        0,0,frame.size.width,frame.size.height))
    window.setContentView_(view)
    monitor=EventReader.alloc().initWithWindow_view_path_config_(
        window,view,state,config)
    # Retain monitor and NSTimer; otherwise Python GC can tear down callback.
    global _KEEPALIVE
    _KEEPALIVE = (window, view, monitor)
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        .05,monitor,"tick:",None,True)
    _KEEPALIVE = (window, view, monitor, timer)
    print("exCADmple teacher overlay ready. Switch to Fusion; the overlay never takes your mouse.")
    app.run()


def calibrate(config):
    # Calibrate anchors without altering Fusion; hover on screen and Return
    # in Terminal. Coordinates measured from Quartz global origin (top-left).
    try:
        import Quartz
        from AppKit import NSScreen
    except ImportError:
        print("Install pyobjc-framework-Quartz too.")
        raise
    frame=NSScreen.mainScreen().frame()
    w,h=frame.size.width,frame.size.height
    anchors={}
    for key,prompt in (
        ("tool","Hover over Fusion's toolbar tool location"),
        ("reference","Hover over the middle of the reference model"),
        ("parameter","Hover over where the demonstration field should appear"),
        ("confirm","Hover over its OK/confirmation location")):
        input(prompt+"; press Enter in Terminal without moving the pointer: ")
        pt=Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        anchors[key]=[max(0,min(1,float(pt.x)/w)),
                      max(0,min(1,1-float(pt.y)/h))]
        print(key,anchors[key])
    config.parent.mkdir(parents=True,exist_ok=True)
    config.write_text(json.dumps(anchors,indent=2),encoding="utf-8")
    print("Saved",config)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--calibrate",action="store_true")
    parser.add_argument("--config",type=Path,default=CONFIG_FILE)
    parser.add_argument("--state",type=Path,default=STATE_FILE)
    args=parser.parse_args()
    if sys.platform!="darwin":
        parser.error("Requires macOS + Autodesk Fusion Desktop.")
    if args.calibrate:
        calibrate(args.config)
    else:
        run(args.config,args.state)
