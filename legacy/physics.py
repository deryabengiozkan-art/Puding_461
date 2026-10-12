"""
Description: Physics of the archery game for ME461 course.
Author: Derya Bengi Özkan, Mehmet Necati Özyetiş, Ali Erkan Ünal
Version : 1.1

"""

#------------------Libaries------------------#

import math
import numpy as np


#------------------Constants------------------#

First_Circle_Pts = 50
Second_Circle_Pts = 25
Third_Circle_Pts = 15

Arrow_Max_Speed = 100
Archer_Height = 1.4

Target_Distance = 10.0                          # distance between the archer and the target, we will find that by camera feedback
Target_Height = 1.0                            # height of the target, we will find that by camera feedback


#-----------------Mechanics------------------#

def Trajectory(speed, angle):               # speed in m/s, angle in degrees

    # The arrows trajectory will be formed of second order polynomial in the form of ax^2 + bx +c
    coefficents = [-9.81/2, math.sin(math.radians(angle))*speed, Archer_Height]
    roots = np.roots(coefficents)
    t= roots[0] if roots[0] > 0 else roots[1]
    x= speed * math.cos(math.radians(angle)) * t


    b = math.tan(math.radians(angle))
    c = Archer_Height
    a = ((-c-b*x)/x**2)

    return a,b,c

def Score_Calculator(speed, angle):

    if speed * math.cos(math.radians(angle)) <= 0:     # arrow does not move towards the target (zero speed or angle >= 90)
        return 0

    a,b,c = Trajectory(speed, angle)
    x = Target_Distance
    y = a*x**2 + b*x + c

    if (y > Target_Height + 0.5) or (y < Target_Height - 0.5):
        return 0
    elif (y > Target_Height + 0.4) or (y < Target_Height - 0.4):
        return Third_Circle_Pts
    elif (y > Target_Height + 0.2) or (y < Target_Height - 0.2):
        return Second_Circle_Pts
    else:
        return First_Circle_Pts
