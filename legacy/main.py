"""
Description: This is a simple game for ME461 course.
Author: Derya Bengi Özkan, Mehmet Necati Özyetiş, Ali Erkan Ünal
Version : 1.1

"""

#------------------Libaries------------------#

import pygame
from pygame.locals import *

from physics import Score_Calculator


#------------------Game-----------------------#

#------------------Constants------------------#
Screen_Width = 800
Screen_Height = 600
FPS = 60

Play_button =pygame.Rect(350, 250, 100, 50)
Calibrate_button = pygame.Rect(350, 350, 100, 50)
Calibrate_quit_button = pygame.Rect(350, 450, 100, 50)
Reset_button = pygame.Rect(350, 250, 100, 50)

Shooting_angle: float = 0.0                     # initial shooting angle, we will fing that by camera feedback
Shooting_Speed: float = 0.0                     # initial shooting speed, we will calculate that by camera feedback

Total_score = 0
Shots = 0
Max_Shots = 3

STATE_MENU = "MENU"
STATE_PLAY = "PLAY"
STATE_CALIBRATE = "CALIBRATE"
STATE_FINISH = "FINISH"

current_state = STATE_MENU

GRAY = (128, 128, 128)
RED = (255, 0, 0)
GREEN = (0, 255, 0)

background = GREEN

pygame.init()
screen = pygame.display.set_mode((Screen_Width, Screen_Height))
clock = pygame.time.Clock()

pygame.display.set_caption("Archidon")

screen.fill(background)
pygame.display.update()


#------------------Game Loop------------------#

running = True

while running:
    for event in pygame.event.get():                #Closes the game when the user clicks the close button
        if event.type == pygame.QUIT:
            running = False

        #print(event)                               #Debugging purposes, prints the event to the console
        if event.type == pygame.MOUSEBUTTONDOWN:    #Checks if the mouse button is pressed down
            mouse_x, mouse_y = pygame.mouse.get_pos()

            if current_state == STATE_MENU:

                if Play_button.collidepoint(mouse_x, mouse_y):  #Checks if the mouse click is inside the play button
                    current_state = STATE_PLAY
                    Total_score = 0
                    Shots = 0
                    print("Play button clicked")

                elif Calibrate_button.collidepoint(mouse_x, mouse_y):  #Checks if the mouse click is inside the calibrate button
                    current_state = STATE_CALIBRATE
                    print("Calibrate button clicked")

            elif current_state == STATE_CALIBRATE:

                #Burada kalibrasyonu tamamladıktan sonra butona bastığımızı varsayıyorum

                if Calibrate_quit_button.collidepoint(mouse_x, mouse_y):  #Checks if the mouse click is inside the calibrate quit button
                    current_state = STATE_MENU
                    print("Calibrate quit button clicked")

            elif current_state == STATE_FINISH:

                if Reset_button.collidepoint(mouse_x, mouse_y):  #Checks if the mouse click is inside the reset button
                    current_state = STATE_MENU
                    Total_score = 0
                    Shots = 0
                    print("reset button clicked")

        # After there i put an workaround for the image processing to test the mechanics of the game, we will remove this part after the image processing is done
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                if current_state == STATE_PLAY:
                    # we should detect the arrow and calculate the speed and angle of the arrow, then we should calculate the score based on the speed and angle of the arrow
                    #
                    # For now we will use random values for speed and angle, we will replace this part with the image processing part
                    Shooting_angle = 45.0
                    Shooting_Speed = 50.0
                    score = Score_Calculator(Shooting_Speed, Shooting_angle)
                    Total_score += score
                    Shots += 1
                    print(f"Shot {Shots}: Speed: {Shooting_Speed}, Angle: {Shooting_angle}, Score: {score}, Total Score: {Total_score}")

                    if Shots >= Max_Shots:
                        current_state = STATE_FINISH
                        print("Max shots reached,  total score: ", Total_score)

    screen.fill(background)                                     #Starting Screen or menu screen @necati


    if current_state == STATE_MENU:
        pygame.draw.rect(screen, RED, Play_button)              #Draws the play button @Necati
        pygame.draw.rect(screen, RED, Calibrate_button)         #Draws the calibrate button @Necati

    elif current_state == STATE_PLAY:
        #Game logic goes here
        # we should detect the arrow and calculate the speed and angle of the arrow, then we should calculate the score based on the speed and angle of the arrow
        #
        pass

    elif current_state == STATE_CALIBRATE:
        pygame.draw.rect(screen, RED, Calibrate_quit_button)     #Draws the calibrate quit button

    elif current_state == STATE_FINISH:
        pygame.draw.rect(screen, GRAY, Reset_button)             #Draws the reset button

    pygame.display.update()
    clock.tick(FPS)


pygame.quit()
