"""A hand-authored starting phone-stand mesh, not modeling-operation replay.

The two upper faces are separate polygons so the learner can actually pick
and extrude the rear face with Blender's standard E operator. Constructing
an editable starter mesh is distinct from reimplementing Extrude/Inset/Bevel.
"""
HALF_X=1.65
REAR_Y=.75
BACK_Y=1.15
FRONT_Y=-1.15
THICKNESS=.24


def practice_mesh():
    ys=(FRONT_Y,REAR_Y,BACK_Y)
    verts=[(x,y,z) for x in (-HALF_X,HALF_X) for y in ys for z in (0.0,THICKNESS)]
    def ix(x,y,z):return (x*3+y)*2+z
    faces=[]
    for y in range(2):
        faces += [
            (ix(0,y,1),ix(1,y,1),ix(1,y+1,1),ix(0,y+1,1)),
            (ix(0,y+1,0),ix(1,y+1,0),ix(1,y,0),ix(0,y,0)),
            (ix(0,y,0),ix(0,y,1),ix(0,y+1,1),ix(0,y+1,0)),
            (ix(1,y+1,0),ix(1,y+1,1),ix(1,y,1),ix(1,y,0)),
        ]
    faces += [
        (ix(0,0,0),ix(1,0,0),ix(1,0,1),ix(0,0,1)),
        (ix(1,2,0),ix(0,2,0),ix(0,2,1),ix(1,2,1)),
    ]
    return verts,faces
