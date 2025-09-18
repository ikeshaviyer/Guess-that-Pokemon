import os
import sys
import time
from bs4 import BeautifulSoup
import requests
from PIL import Image, ImageOps, ImageSequence
from io import BytesIO
import pygame
import numpy as np
import cv2
import random
import serial
import serial.tools.list_ports

# Initialize global variables for Arduino connection
arduino = None
arduino_connected = False

def find_arduino_port():
    global arduino
    global arduino_connected
    
    try:
        ports = list(serial.tools.list_ports.comports())
        print("Available ports:")
        for port in ports:
            print(f"{port.device}: {port.description}")
            
            try:
                # Check if port description contains "Arduino"
                if "Arduino" in port.description:
                    print(f"Arduino found on {port.device}")
                    time.sleep(2)  # Small delay before trying to open the port
                    try:
                        arduino = serial.Serial(port.device, 9600, timeout=1)
                        arduino_connected = True
                        print(f"Successfully connected to {port.device}")
                        return
                    except Exception as e:
                        print(f"Failed to connect to {port.device}: {e}")
                        continue
            except Exception as e:
                print(f"Error while checking {port.device}: {e}")
                continue
    except Exception as e:
        print(f"Error scanning for Arduino ports: {e}")
    
    arduino_connected = False
    print("No Arduino found.")

# Call the find_arduino_port function at the start
find_arduino_port()

# Set up paths for sound files
current_dir = os.path.dirname(os.path.abspath(__file__))
correct_sound_path = os.path.join(current_dir, 'correct.wav')
incorrect_sound_path = os.path.join(current_dir, 'incorrect.wav')
background_music_path = os.path.join(current_dir, 'bgm.mp3')
background_gif_path = os.path.join(current_dir, 'bg.gif')

# Pygame setup
pygame.init()

# Load the GIF and get the size of the first frame
background_gif = Image.open(background_gif_path)
bg_width, bg_height = background_gif.size

# Adjust window size to match the GIF
screen = pygame.display.set_mode((bg_width, bg_height))
pygame.display.set_caption("Guess That Pokémon")

# Initialize the mixer for sound
pygame.mixer.init()

# Load the sound effects
correct_sound = pygame.mixer.Sound(correct_sound_path)
incorrect_sound = pygame.mixer.Sound(incorrect_sound_path)

# Load and play background music on loop
pygame.mixer.music.load(background_music_path)
pygame.mixer.music.play(-1)  # -1 means loop indefinitely
pygame.mixer.music.set_volume(0.5)  # Set volume (0.0 to 1.0)

font1_path = os.path.join(current_dir, 'Pokemon Solid.ttf')

# Define colors
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
GRAY = (200, 200, 200)

# Load font
font = pygame.font.Font(None, 36)
font1 = pygame.font.Font(font1_path, 36)

# Function to fetch Pokémon data
def fetch_pokemon_data():
    url = "https://pokemondb.net/pokedex/national"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    pokemon_data = []
    
    for infocard in soup.find_all('div', class_='infocard'):
        name_tag = infocard.find('a', class_='ent-name')
        img_tag = infocard.find('img', class_='img-sprite')
        
        if name_tag and img_tag:
            name = name_tag.text.lower()
            img_url = img_tag['src']
            pokemon_data.append((name, img_url))
    
    return pokemon_data

# Function to fetch Pokémon image
def fetch_pokemon_image(img_url):
    response = requests.get(img_url)
    img_data = response.content
    img = Image.open(BytesIO(img_data))
    return img

# Convert an image to a silhouette by magic wand selection
def create_silhouette(image):
    image = image.convert("RGBA")
    np_image = np.array(image)
    bgr_image = cv2.cvtColor(np_image, cv2.COLOR_RGBA2BGR)
    
    flood_fill_image = bgr_image.copy()
    h, w = flood_fill_image.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    tolerance = (10, 5, 10)  # Slight tolerance to account for slight background variations
    cv2.floodFill(flood_fill_image, mask, (0, 0), (255, 255, 255), tolerance, tolerance, flags=cv2.FLOODFILL_MASK_ONLY | (255 << 8))
    
    mask = mask[1:-1, 1:-1]  # Remove the extra border added during flood fill
    silhouette_mask = cv2.bitwise_not(mask)
    
    kernel = np.ones((3, 3), np.uint8)
    silhouette_mask = cv2.dilate(silhouette_mask, kernel, iterations=1)
    silhouette_mask = cv2.erode(silhouette_mask, kernel, iterations=1)
    
    silhouette_mask = cv2.GaussianBlur(silhouette_mask, (5, 5), 0)
    
    normalized_mask = silhouette_mask / 255.0
    
    silhouette_rgba = np.ones_like(np_image) * 255  # start with a white canvas
    for c in range(4):  # Apply feathering to each channel
        silhouette_rgba[:, :, c] = silhouette_rgba[:, :, c] * (1 - normalized_mask) + BLACK[c] * normalized_mask
    
    final_image = Image.fromarray(silhouette_rgba.astype('uint8'), "RGBA")
    
    return final_image

# Convert GIF frames to Pygame Surfaces
def load_gif_frames(gif_path):
    pil_image = Image.open(gif_path)
    frames = []
    for frame in ImageSequence.Iterator(pil_image):
        frame = frame.convert("RGBA")
        mode = frame.mode
        size = frame.size
        data = frame.tobytes()
        surface = pygame.image.fromstring(data, size, mode)
        frames.append(surface)
    return frames

# Display the background animation
def display_background(frames, frame_index):
    surface = frames[frame_index]
    screen.blit(surface, (0, 0))
    frame_index = (frame_index + 1) % len(frames)
    return frame_index

# Display the silhouette in Pygame
def display_silhouette(pil_image):
    pil_image = pil_image.convert("RGBA")
    mode = pil_image.mode
    size = pil_image.size
    data = pil_image.tobytes()
    surface = pygame.image.fromstring(data, size, mode)
    surface_rect = surface.get_rect(center=(bg_width // 2, bg_height // 2))
    screen.blit(surface, surface_rect.topleft)

# Display the actual image with a fade-in effect
def display_actual_image_with_fade(pil_image, duration=2):
    pil_image = pil_image.convert("RGBA")
    mode = pil_image.mode
    size = pil_image.size
    alpha_step = int(255 / (duration * 60))  # Assuming 60 FPS
    
    for alpha in range(0, 256, alpha_step):
        overlay_image = pil_image.copy()
        overlay_image.putalpha(alpha)
        mode = overlay_image.mode
        data = overlay_image.tobytes()
        surface = pygame.image.fromstring(data, size, mode)
        surface_rect = surface.get_rect(center=(bg_width // 2, bg_height // 2))
        screen.blit(surface, surface_rect.topleft)
        pygame.display.flip()
        pygame.time.wait(int(1000 / 60))

# Display the Pokémon name above the image
def display_pokemon_name(name):
    name_surface = font1.render(name.title(), True, BLACK[:3])
    name_rect = name_surface.get_rect(center=(bg_width // 2, 100))
    screen.blit(name_surface, name_rect)

def draw_textbox(text):
    input_box = pygame.Rect(bg_width // 2 - 150, bg_height - 100, 300, 40)
    pygame.draw.rect(screen, WHITE[:3], input_box)
    txt_surface = font.render(text, True, BLACK[:3])
    width = max(300, txt_surface.get_width() + 10)
    input_box.w = width
    screen.blit(txt_surface, (input_box.x + 5, input_box.y + 5))
    pygame.draw.rect(screen, BLACK[:3], input_box, 2)

# Display the play screen
def play_screen():
    screen.fill(WHITE[:3])
    welcome_surface = font1.render("Welcome to Guess That Pokémon!", True, BLACK[:3])
    instructions_surface = font.render("Press ENTER to Start", True, BLACK[:3])
    welcome_rect = welcome_surface.get_rect(center=(bg_width // 2, bg_height // 2 - 100))
    instructions_rect = instructions_surface.get_rect(center=(bg_width // 2, bg_height // 2 + 100))
    screen.blit(welcome_surface, welcome_rect)
    screen.blit(instructions_surface, instructions_rect)
    
    # Display Arduino connection status
    if arduino_connected:
        status_surface = font.render("Connected", True, BLACK[:3])
    else:
        status_surface = font.render("Not Connected", True, BLACK[:3])
    status_rect = status_surface.get_rect(bottomright=(bg_width - 20, bg_height - 20))
    screen.blit(status_surface, status_rect)
    
    pygame.display.flip()
    
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    waiting = False

# Display the game over screen
def game_over_screen(points):
    screen.fill(WHITE[:3])
    game_over_surface = font1.render("Game Over!", True, BLACK[:3])
    points_surface = font1.render(f"Total Points: {points}", True, BLACK[:3])
    instructions_surface = font.render("Press ENTER to return to title", True, BLACK[:3])
    game_over_rect = game_over_surface.get_rect(center=(bg_width // 2, bg_height // 2 - 100))
    points_rect = points_surface.get_rect(center=(bg_width // 2, bg_height // 2))
    instructions_rect = instructions_surface.get_rect(center=(bg_width // 2, bg_height // 2 + 100))
    screen.blit(game_over_surface, game_over_rect)
    screen.blit(points_rect, points_rect)
    screen.blit(instructions_surface, instructions_rect)
    pygame.display.flip()
    
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    waiting = False
                    main()

# Display the you win screen
def you_win_screen(points, total_rounds):
    screen.fill(WHITE)
    you_win_surface = font1.render("You Win!", True, BLACK[:3])
    points_surface = font1.render(f"Score: {points} / {total_rounds}", True, BLACK[:3])
    instructions_surface = font.render("Press ENTER to return to title", True, BLACK[:3])
    you_win_rect = you_win_surface.get_rect(center=(bg_width // 2, bg_height // 2 - 100))
    points_rect = points_surface.get_rect(center=(bg_width // 2, bg_height // 2))
    instructions_rect = instructions_surface.get_rect(center=(bg_width // 2, bg_height // 2 + 100))
    screen.blit(you_win_surface, you_win_rect)
    screen.blit(points_surface, points_rect)
    screen.blit(instructions_surface, instructions_rect)
    pygame.display.flip()

    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    waiting = False
                    main()

def send_high():
    if arduino_connected:
        try:
            arduino.write(b'H')  # Send 'H' to Arduino
            # Don't block the game - Arduino will handle timing
        except Exception as e:
            print(f"Arduino communication error: {e}")

def send_low():
    if arduino_connected:
        try:
            arduino.write(b'L')  # Send 'L' to Arduino
        except Exception as e:
            print(f"Arduino communication error: {e}")

def handle_incorrect_guess(pokemon_img, pokemon_name):
    display_actual_image_with_fade(pokemon_img)
    display_pokemon_name(pokemon_name)
    send_high()
    pygame.display.flip()
    pygame.time.wait(4000)  # Wait for 3 seconds to show the correct name

def main_game():
    running = True
    user_text = ""
    result_text = ""
    points = 0
    total_rounds = 10
    current_round = 1
    
    # Game state variables
    game_state = "guessing"  # "guessing", "showing_result", "transitioning"
    transition_start_time = 0
    arduino_signal_sent = False
    arduino_low_sent = False

    # Timer related variables
    time_limit = 5  # 5 seconds limit per round
    start_time = time.time()

    # Fetch Pokémon data
    pokemon_data = fetch_pokemon_data()

    # Randomly select a Pokémon
    pokemon_name, pokemon_img_url = random.choice(pokemon_data)
    pokemon_img = fetch_pokemon_image(pokemon_img_url)
    silhouette = create_silhouette(pokemon_img)

    bg_frames = load_gif_frames(background_gif_path)
    frame_index = 0
    
    # Clear any existing events in the queue
    pygame.event.clear()

    while running:
        frame_index = display_background(bg_frames, frame_index)
        
        # Handle different game states
        if game_state == "guessing":
            display_silhouette(silhouette)
            
            # Calculate remaining time and check if time is up
            elapsed_time = time.time() - start_time
            if elapsed_time > time_limit:
                result_text = f"Time's Up! It was {pokemon_name.title()}"
                game_state = "showing_result"
                transition_start_time = time.time()
                arduino_signal_sent = False  # Reset Arduino signal flags
                arduino_low_sent = False
                # Clear input buffer when transitioning
                pygame.event.clear()
                user_text = ""
                
        elif game_state == "showing_result":
            # Show the result - display image and name without fade (static display)
            pil_image = pokemon_img.convert("RGBA")
            mode = pil_image.mode
            size = pil_image.size
            data = pil_image.tobytes()
            surface = pygame.image.fromstring(data, size, mode)
            surface_rect = surface.get_rect(center=(bg_width // 2, bg_height // 2))
            screen.blit(surface, surface_rect.topleft)
            display_pokemon_name(pokemon_name)
            
            # Send Arduino signal only for incorrect answers (not for correct answers)
            if not arduino_signal_sent and result_text != "Correct!":
                send_high()
                arduino_signal_sent = True
            
            # Send LOW signal after 2.5 seconds to turn off Arduino signal (only if HIGH was sent)
            if not arduino_low_sent and arduino_signal_sent and time.time() - transition_start_time > 2.5:
                send_low()
                arduino_low_sent = True
            
            # Wait for transition period
            if time.time() - transition_start_time > 3.0:  # Show result for 3 seconds
                game_state = "transitioning"
                transition_start_time = time.time()
                
        elif game_state == "transitioning":
            # Brief transition period to prevent input carryover
            if time.time() - transition_start_time > 0.5:  # 0.5 second buffer
                current_round += 1
                if current_round <= total_rounds:
                    # Start new round
                    pokemon_name, pokemon_img_url = random.choice(pokemon_data)
                    pokemon_img = fetch_pokemon_image(pokemon_img_url)
                    silhouette = create_silhouette(pokemon_img)
                    start_time = time.time()
                    result_text = ""
                    user_text = ""
                    game_state = "guessing"
                    arduino_signal_sent = False  # Reset Arduino signal flags
                    arduino_low_sent = False
                    # Clear any accumulated events
                    pygame.event.clear()
                else:
                    running = False
                    you_win_screen(points, total_rounds)

        # Draw the text box only during guessing state
        if game_state == "guessing":
            draw_textbox(user_text)

        # Display the result of the guess in the upper part of the screen
        if result_text:
            result_surface = font.render(result_text, True, BLACK[:3])
            screen.blit(result_surface, (bg_width // 2 - (result_surface.get_width() // 2), 150))  # Upper part of screen

        points_surface = font.render(f"Points: {points}", True, BLACK[:3])
        screen.blit(points_surface, (100, 50))
        round_surface = font.render(f"Round: {current_round} / {total_rounds}", True, BLACK[:3])
        screen.blit(round_surface, (bg_width - 200, 50))

        # Display the countdown timer (only during guessing)
        if game_state == "guessing":
            elapsed_time = time.time() - start_time
            remaining_time = max(0, time_limit - elapsed_time)
            timer_surface = font.render(f"Time: {remaining_time:.1f}s", True, BLACK[:3])
            screen.blit(timer_surface, (20, bg_height - 50))

        # Event handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                # Only process input during guessing state
                if game_state == "guessing":
                    if event.key == pygame.K_RETURN:
                        if user_text.lower() == pokemon_name:
                            points += 1
                            result_text = "Correct!"
                            correct_sound.play()  # Play correct sound
                            game_state = "showing_result"
                            transition_start_time = time.time()
                            arduino_signal_sent = False  # Reset Arduino signal flags
                            arduino_low_sent = False
                            # Clear input buffer when transitioning
                            pygame.event.clear()
                        else:
                            result_text = f"It was {pokemon_name.title()}"
                            incorrect_sound.play()  # Play incorrect sound
                            game_state = "showing_result"
                            transition_start_time = time.time()
                            arduino_signal_sent = False  # Reset Arduino signal flags
                            arduino_low_sent = False
                            # Clear input buffer when transitioning
                            pygame.event.clear()
                            user_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        user_text = user_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        game_over_screen(points)
                    else:
                        # Only add printable characters
                        if event.unicode.isprintable() and len(user_text) < 20:
                            user_text += event.unicode
                # Allow escape to work in any state
                elif event.key == pygame.K_ESCAPE:
                    game_over_screen(points)

        pygame.display.flip()

    pygame.quit()

def main():
    play_screen()
    main_game()

if __name__ == "__main__":
    main()