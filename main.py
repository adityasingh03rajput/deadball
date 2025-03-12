from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle
import random

# Set window size for desktop (will be ignored on Android)
Window.size = (800, 600)

class Game(Widget):
    def __init__(self, **kwargs):
        super(Game, self).__init__(**kwargs)
        self.ball_pos = [400, 300]
        self.ball_velocity = [5, 5]
        self.player_pos = [100, 100]
        self.score = 0
        self.game_over = False
        self.bind(size=self.update_canvas)
        Clock.schedule_interval(self.update, 1.0 / 60.0)

    def update_canvas(self, *args):
        self.canvas.clear()
        with self.canvas:
            # Draw background
            Color(0, 0, 0, 1)
            Rectangle(pos=(0, 0), size=self.size)

            # Draw ball
            Color(1, 0, 0, 1)
            Ellipse(pos=(self.ball_pos[0] - 15, self.ball_pos[1] - 15), size=(30, 30))

            # Draw player
            Color(0, 0, 1, 1)
            Rectangle(pos=(self.player_pos[0] - 20, self.player_pos[1] - 20), size=(40, 40))

    def update(self, dt):
        if not self.game_over:
            # Update ball position
            self.ball_pos[0] += self.ball_velocity[0]
            self.ball_pos[1] += self.ball_velocity[1]

            # Ball collision with walls
            if self.ball_pos[0] <= 0 or self.ball_pos[0] >= self.width:
                self.ball_velocity[0] *= -1
            if self.ball_pos[1] <= 0 or self.ball_pos[1] >= self.height:
                self.ball_velocity[1] *= -1

            # Ball collision with player
            if (abs(self.ball_pos[0] - self.player_pos[0]) < 30 and
                    abs(self.ball_pos[1] - self.player_pos[1]) < 30):
                self.score += 1
                self.ball_pos = [random.randint(100, 700), random.randint(100, 500)]
                self.ball_velocity = [random.choice([-5, 5]), random.choice([-5, 5])]

            # Update canvas
            self.update_canvas()

    def on_touch_move(self, touch):
        # Move player to touch position
        self.player_pos = [touch.x - 20, touch.y - 20]

    def reset_game(self):
        # Reset game state
        self.ball_pos = [400, 300]
        self.ball_velocity = [5, 5]
        self.player_pos = [100, 100]
        self.score = 0
        self.game_over = False

class GameApp(App):
    def build(self):
        # Create layout
        layout = BoxLayout(orientation='vertical')

        # Add score label
        self.score_label = Label(text="Score: 0", size_hint=(1, 0.1))
        layout.add_widget(self.score_label)

        # Add game widget
        self.game = Game()
        layout.add_widget(self.game)

        # Add reset button
        reset_button = Button(text="Reset Game", size_hint=(1, 0.1))
        reset_button.bind(on_press=self.reset_game)
        layout.add_widget(reset_button)

        return layout

    def reset_game(self, instance):
        # Reset game state
        self.game.reset_game()
        self.score_label.text = "Score: 0"

if __name__ == '__main__':
    GameApp().run()
