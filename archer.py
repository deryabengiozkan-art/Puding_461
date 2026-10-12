"""An articulated human archer drawn as shaded, antialiased vector shapes.

The shoulders, elbows and wrists form two-segment limbs. Clothes and leather
gear follow those joints; bow and string respond to measured elevation/pull.
The small transparent character surface is cached whenever the pose is unchanged.
"""
import math
import pygame


class ArcherArtist:
    WIDTH, HEIGHT, SCALE = 230, 235, 2
    TIP = pygame.Vector2(28, 94)
    FLOOR = 192

    def __init__(self):
        self.key = None
        self.image = None

    @staticmethod
    def elbow(start, end, length, bend):
        offset = end - start
        distance = offset.length()
        if distance < .001:
            return start + (0, length)
        direction = offset / distance
        normal = pygame.Vector2(-direction.y, direction.x)
        height = math.sqrt(max(0, length * length - (distance / 2) ** 2))
        return (start + end) / 2 + bend * height * normal

    def pose(self, angle, strength, in_flight):
        key = (angle, strength, in_flight)
        if key == self.key:
            return self.image
        self.key = key
        scale = self.SCALE
        canvas = pygame.Surface((self.WIDTH * scale, self.HEIGHT * scale), pygame.SRCALPHA)

        def pt(p):
            return round(p[0] * scale), round(p[1] * scale)

        def polygon(color, vertices):
            pygame.draw.polygon(canvas, color, [pt(v) for v in vertices])

        def circle(color, center, radius):
            pygame.draw.circle(canvas, color, pt(center), round(radius * scale))

        def limb(start, end, width, color, highlight=None):
            pygame.draw.line(canvas, color, pt(start), pt(end), round(width * scale))
            circle(color, start, width / 2)
            circle(color, end, width / 2)
            if highlight:
                shift = pygame.Vector2(-1.5, -1.5)
                pygame.draw.line(canvas, highlight, pt(start + shift), pt(end + shift), max(1, round(width * .25 * scale)))

        shoulder = pygame.Vector2(116, 94)
        hip = pygame.Vector2(128, 139)
        forward_foot = pygame.Vector2(92, self.FLOOR)
        rear_foot = pygame.Vector2(169, self.FLOOR)
        forward_knee = pygame.Vector2(111, 164)
        rear_knee = pygame.Vector2(153, 163)
        radians = math.radians(angle)
        direction = pygame.Vector2(-math.cos(radians), -math.sin(radians))
        normal = pygame.Vector2(-direction.y, direction.x)
        bow_hand = self.TIP - 22 * direction
        pull = .05 if in_flight else strength
        draw_hand = bow_hand - (18 + 54 * pull) * direction
        bow_elbow = self.elbow(shoulder, bow_hand, 44, -1)
        draw_shoulder = shoulder + (9, 1)
        draw_elbow = self.elbow(draw_shoulder, draw_hand, 34, -1)

        pygame.draw.ellipse(canvas, (7, 17, 17, 90), (78*scale, 188*scale, 116*scale, 14*scale))
        # Rear leg and boots; slightly bent knees keep a stable shooting stance.
        for knee, foot, color in ((rear_knee, rear_foot, (64, 68, 54)),
                                  (forward_knee, forward_foot, (89, 94, 71))):
            limb(hip, knee, 13, color, (121, 124, 93))
            limb(knee, foot + (0, -11), 11, color, (110, 117, 88))
            limb(foot + (0, -14), foot + (0, -3), 13, (68, 45, 32), (119, 82, 49))
            polygon((56, 38, 30), [foot+(-7,-7), foot+(5,-7), foot+(10,-2), foot+(10,2), foot+(-12,2), foot+(-12,-2)])
            limb(foot + (-11, 2), foot + (10, 2), 2, (33, 31, 27))

        # Back drawing arm, shaded sleeves, forearm and bracer.
        limb(draw_shoulder, draw_elbow, 13, (33, 60, 47), (64, 97, 69))
        limb(draw_elbow, draw_hand, 9, (186, 133, 98), (232, 184, 137))
        bracer_end = draw_elbow + .43 * (draw_hand - draw_elbow)
        limb(draw_elbow, bracer_end, 10, (80, 52, 36), (148, 98, 58))

        # Fitted tunic silhouette, seams, shoulder cape and belt.
        polygon((27, 48, 39), [shoulder+(-8,-5), shoulder+(16,-2), hip+(12,-2), hip+(9,9), hip+(-16,9), shoulder+(-11,7)])
        polygon((52, 86, 60), [shoulder+(-5,-5), shoulder+(8,-3), hip+(7,-2), hip+(-12,4), shoulder+(-8,8)])
        polygon((79, 114, 79), [shoulder+(-6,-5), shoulder+(0,-4), hip+(-4,-1), hip+(-9,0)])
        limb(shoulder+(7,10), hip+(3,-6), 2, (23, 44, 37))
        polygon((38, 62, 48), [shoulder+(-13,-5), shoulder+(19,-8), shoulder+(20,15), shoulder+(-5,8)])
        limb(hip+(-16,1), hip+(13,-1), 6, (75, 46, 29), (151, 103, 49))
        polygon((188, 157, 87), [hip+(-2,-3), hip+(5,-3), hip+(5,4), hip+(-2,4)])
        polygon((54, 38, 27), [hip+(0,-1), hip+(3,-1), hip+(3,2), hip+(0,2)])
        # Quiver follows the back and carries spare arrow fletching.
        limb(shoulder+(23,8), hip+(16,-10), 14, (75, 48, 31), (140, 99, 58))
        for x in (134, 139, 144):
            limb(pygame.Vector2(x, 102), pygame.Vector2(x+9, 57), 2, (152, 119, 70))
            polygon((164, 155, 131), [(x+6,66), (x+8,53), (x+14,58), (x+10,68)])
        limb(shoulder+(-8,1), hip+(13,-4), 5, (94, 65, 42), (151, 111, 66))

        # Neck, ear, jaw, nose and hood: restrained proportions and face profile.
        limb(shoulder+(4,-7), shoulder+(3,-21), 9, (178, 124, 88), (231, 177, 126))
        head = pygame.Vector2(119, 65)
        polygon((30, 46, 37), [head+(-9,-12), head+(10,-15), head+(17,-2), head+(15,19), head+(1,25), head+(-10,12)])
        polygon((58, 81, 55), [head+(-8,-11), head+(8,-13), head+(10,14), head+(2,21), head+(-6,12)])
        polygon((216, 164, 119), [head+(-10,-4), head+(2,-4), head+(7,7), head+(2,15), head+(-7,15), head+(-12,8)])
        polygon((230, 178, 132), [head+(-10,-4), head+(-8,2), head+(-16,6), head+(-11,9), head+(-7,13), head+(-4,1)])
        circle((191, 133, 94), head+(5,5), 3)
        limb(head+(-10,1), head+(-5,1), 2, (51, 43, 35))
        circle((238, 226, 194), head+(-8,1), 1)
        limb(head+(-10,11), head+(-5,12), 1, (102, 64, 47))
        polygon((109, 75, 53), [head+(-8,13), head+(2,12), head+(1,16), head+(-6,16)])
        polygon((72, 96, 63), [head+(-13,-6), head+(-7,-14), head+(8,-15), head+(11,-7), head+(-8,-5)])

        limb(shoulder, bow_elbow, 12, (57, 95, 66), (94, 132, 87))
        limb(bow_elbow, bow_hand, 8, (189, 139, 97), (237, 189, 138))
        bracer = bow_hand + .36 * (bow_elbow - bow_hand)
        limb(bracer, bow_hand+(2,0), 9, (88, 54, 35), (154, 106, 61))
        circle((220, 166, 116), bow_hand, 4)
        circle((220, 166, 116), draw_hand, 4)

        # Wooden recurve limbs, grip, silver string and held arrow.
        top = bow_hand + 48 * normal - 10 * direction
        bottom = bow_hand - 48 * normal - 10 * direction
        middle = bow_hand + 24 * direction
        curve = [(1-t)**2*top + 2*(1-t)*t*middle + t*t*bottom for t in (i/32 for i in range(33))]
        pygame.draw.lines(canvas, (48, 31, 23), False, [pt(v) for v in curve], 6*scale)
        pygame.draw.lines(canvas, (160, 112, 67), False, [pt(v) for v in curve], 3*scale)
        pygame.draw.lines(canvas, (219, 180, 107), False, [pt(v) for v in curve], scale)
        limb(bow_hand-6*normal, bow_hand+6*normal, 6, (69, 43, 30))
        pygame.draw.lines(canvas, (216, 214, 185), False, [pt(top), pt(draw_hand), pt(bottom)], scale)
        if not in_flight:
            limb(draw_hand, self.TIP, 2, (226, 201, 145))
            polygon((221, 227, 219), [self.TIP, self.TIP-9*direction+3*normal, self.TIP-9*direction-3*normal])
            for shift in (0, 5):
                base = draw_hand + shift * direction
                limb(base, base+5*direction+4*normal, 2, (197, 181, 145))
        self.image = pygame.transform.smoothscale(canvas, (self.WIDTH, self.HEIGHT))
        return self.image

    def draw(self, screen, launch_tip, angle, strength, in_flight):
        image = self.pose(angle, strength, in_flight)
        screen.blit(image, (round(launch_tip[0] - self.TIP.x), round(launch_tip[1] - self.TIP.y)))
