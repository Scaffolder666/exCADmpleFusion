"""Single-viewport custom GPU control panel inspired by History in Motion.

This is a 2D overlay INSIDE Blender's existing 3D Viewport. It is not another
window, split viewport or Scene. The reference and user-authored models remain
in the same physical modeling environment.

All widget hit areas are provided by overlay_geometry, which is also tested
outside Blender. The modal input operator lives in __init__.py so it can
coordinate existing playback actions and N-sidebar visibility.
"""
import math
import textwrap

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from .core import step_at_frame, caption_at_frame, operation_phase
from .overlay_geometry import Rect, panel_layout

PANEL_BG = (.085, .102, .125, .96)
PANEL_BORDER = (.37, .42, .48, 1.)
CARD_BG = (.135, .155, .183, .97)
CARD_SELECTED = (.17, .255, .36, .98)
TEXT = (.94, .95, .96, 1.)
MUTED = (.66, .71, .76, 1.)
ACCENT = (.39, .66, .96, 1.)
WHY_BG = (.17, .18, .20, .99)

_STEP_COLORS = (
    (.44, .67, .97, 1.), (.98, .65, .49, 1.),
    (.61, .82, .69, 1.), (.78, .66, .94, 1.)
)


def _shape(shader, rect, color, radius=0.0):
    """Draw a rounded rectangle (triangle fan) using a Blender GPU shader."""
    radius = min(float(radius), rect.w / 2, rect.h / 2)
    if radius < .5:
        verts = [
            (rect.x, rect.y), (rect.x + rect.w, rect.y),
            (rect.x + rect.w, rect.y + rect.h),
            (rect.x, rect.y + rect.h),
        ]
        indices = ((0, 1, 2), (0, 2, 3))
        batch = batch_for_shader(shader, "TRIS", {"pos": verts}, indices=indices)
    else:
        centers = [
            (rect.x+rect.w-radius, rect.y+radius, -math.pi/2, 0),
            (rect.x+rect.w-radius, rect.y+rect.h-radius, 0, math.pi/2),
            (rect.x+radius, rect.y+rect.h-radius, math.pi/2, math.pi),
            (rect.x+radius, rect.y+radius, math.pi, 3*math.pi/2),
        ]
        ring = []
        for cx,cy,a0,a1 in centers:
            for k in range(7):
                a = a0 + (a1-a0) * k/6
                ring.append((cx+math.cos(a)*radius,cy+math.sin(a)*radius))
        vertices = [(rect.x+rect.w/2,rect.y+rect.h/2)] + ring
        indices = [(0,i,i+1) for i in range(1,len(vertices)-1)]
        indices.append((0,len(vertices)-1,1))
        batch = batch_for_shader(shader,"TRIS",{"pos":vertices},indices=indices)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _text(text,x,y,size=13,color=TEXT,max_width=None):
    font=0
    blf.size(font,int(size))
    blf.color(font,*color)
    rendered=str(text)
    if max_width is not None and len(rendered)>1:
        while len(rendered)>2 and blf.dimensions(font,rendered)[0]>max_width:
            rendered=rendered[:-2]
        if rendered!=str(text):
            rendered=rendered.rstrip()+"..."
    blf.position(font,x,y,0)
    blf.draw(font,rendered)


def _paragraph(message, x, top, width=38, rows=3, size=12, color=TEXT):
    for i,line in enumerate(textwrap.wrap(str(message or ""), width=width)[:rows]):
        _text(line,x,top-15*i,size,color)


def _seconds(scene,step):
    fps=max(1,int(scene.render.fps))
    return "%.1fs / %.1fs"%(
        (scene.frame_current-step["start"])/fps,
        (step["end"]-step["start"])/fps
    )


def draw(context, example, current_speed=1.0):
    """Draw HiM-like cards beside the SAME editable 3D modeling viewport."""
    if not context.region or context.region.type != "WINDOW":
        return None
    scene=context.scene
    steps=example.get("steps",[])
    if not steps:
        return None
    current=step_at_frame(example,scene.frame_current)
    index=next((i for i,s in enumerate(steps) if s["id"]==current["id"]),0)
    layout=panel_layout(context.region.width,context.region.height,index,len(steps))
    if not layout:
        return None

    left=layout["bounds"].x
    top=layout["top"]
    width=layout["bounds"].w
    shader=gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    try:
        _shape(shader,layout["bounds"],PANEL_BORDER,13)
        inner=Rect(left+1,layout["bottom"]+1,width-2,layout["bounds"].h-2)
        _shape(shader,inner,PANEL_BG,12)

        # Header, model identity.
        _text("exCADmple",left+17,top-27,16,TEXT)
        _text("x",layout["buttons"]["close"].x+8,top-31,15,MUTED)
        _text(example.get("title","Preset Design Example"),left+17,top-55,12,MUTED,width-30)

        for key,glyph in (("previous","|<"),("play_pause", "||" if
                       getattr(context.screen,"is_animation_playing",False) else ">"),
                          ("next",">|")):
            box=layout["buttons"][key]
            selected=key=="play_pause"
            _shape(shader,box,ACCENT if selected else CARD_BG,8)
            txtcolor=PANEL_BG if selected else TEXT
            _text(glyph,box.x+box.w/2-9,box.y+10,16,txtcolor)
        _text("PLAYBACK",left+18,top-121,10,MUTED)
        _text(_seconds(scene,current),left+width-100,top-121,10,MUTED)

        # Step progress scrub bar, not native blender scene layout.
        bar=layout["buttons"]["progress"]
        _shape(shader,bar,CARD_BG,5)
        p=max(0.,min(1.,(scene.frame_current-current["start"])/
             max(1,current["end"]-current["start"])))
        if p>0.:
            _shape(shader,Rect(bar.x,bar.y,max(2,bar.w*p),bar.h),ACCENT,5)

        _text("DESIGN STEPS",left+18,top-172,11,MUTED)
        _text("%02d / %02d"%(index+1,len(steps)),left+width-73,top-172,11,MUTED)

        # Colored cards + a vertical timeline: ONLY steps of this example.
        cards=layout["cards"]
        if cards:
            bar_x=left+27
            _shape(shader,Rect(bar_x,cards[-1][1].y+25,2,
                              cards[0][1].y-cards[-1][1].y),(.41,.44,.48,.9))
        for k,box in cards:
            step=steps[k]
            selected=k==index
            _shape(shader,box,CARD_SELECTED if selected else CARD_BG,8)
            color=_STEP_COLORS[k%len(_STEP_COLORS)]
            _shape(shader,Rect(box.x+2,box.y+8,4,box.h-16),color,2)
            _text("%02d"%(k+1),box.x+13,box.y+31,11,color)
            _text(step.get("title","Modeling Step"),box.x+40,box.y+30,
                  13,TEXT if selected else MUTED,box.w-52)
            if selected:
                _text(operation_phase(step,scene.frame_current),box.x+40,
                      box.y+11,10,ACCENT,box.w-52)
            else:
                _text(step.get("tool","CAD"),box.x+40,box.y+11,10,MUTED,box.w-52)

        why=layout["why"]
        _shape(shader,why,WHY_BG,9)
        _text("WHY THIS DECISION",why.x+11,why.y+why.h-20,11,ACCENT)
        _paragraph(current.get("reasoning","No rationale recorded."),
                   why.x+11,why.y+why.h-37,width=38,
                   rows=2 if why.h<70 else 3,size=11,color=TEXT)

        if layout["transcript"]:
            t=layout["transcript"]
            _text("NARRATION / CAPTIONS",t.x+2,t.y+t.h-12,10,MUTED)
            _paragraph(caption_at_frame(current,scene.frame_current),
                       t.x+2,t.y+t.h-30,39,2,11,TEXT)

        # Speed controls work on the original Blender scene playback clock
        # in this prototype (documented limitation).
        minus=layout["buttons"]["speed_minus"]
        plus=layout["buttons"]["speed_plus"]
        _text("SPEED",left+18,minus.y+10,11,MUTED)
        _shape(shader,minus,CARD_BG,6)
        _shape(shader,plus,CARD_BG,6)
        _text("-",minus.x+10,minus.y+5,17,TEXT)
        _text("+",plus.x+9,plus.y+5,17,TEXT)
        _text("%.2gx"%current_speed,minus.x+40,minus.y+8,11,TEXT)
    finally:
        gpu.state.blend_set("NONE")
    return layout
