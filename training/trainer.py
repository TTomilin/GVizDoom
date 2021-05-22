import logging
import numpy as np
from time import sleep, time

from .agent import Agent


class AsynchronousTrainer:
    def __init__(self,
                 agent: Agent,
                 decay_epsilon: bool,
                 model_save_freq: int,
                 memory_update_freq: int,
                 train_report_freq: int,
                 train_iterations: int,
                 initial_epsilon = 1.0,
                 final_epsilon = 0.001
                 ):

        self.agent = agent
        self.train_iterations = train_iterations

        if not decay_epsilon:
            self.agent.explore = 0

        # Learning rate
        self.initial_epsilon = initial_epsilon
        self.final_epsilon = final_epsilon
        self.agent.epsilon = self.initial_epsilon if decay_epsilon else self.final_epsilon

        # Frequencies
        self.model_save_freq = model_save_freq
        self.memory_update_freq = memory_update_freq
        self.train_report_freq = train_report_freq

    def train(self):

        # Wait for sufficient experience to be collected
        while self.agent.memory.buffer_size < self.agent.observe:
            sleep(1)
        print('Training Started')

        Q_values = []
        losses = []
        start_time = time()

        for iteration in range(1, self.train_iterations):

            # Update epsilon
            if self.agent.epsilon > self.final_epsilon:
                new_epsilon = self.agent.epsilon - (self.initial_epsilon - self.final_epsilon) / self.agent.explore
                self.agent.epsilon = max(self.final_epsilon, new_epsilon)

            # Train the model
            try:
                Q_max, loss = self.agent.train(iteration)
                Q_values.append(Q_max)
                losses.append(loss)
            except Exception as error:
                logging.error(f'Training agent unsuccessful: {error}')

            # Print mean Q_max & mean loss
            if not iteration % self.train_report_freq:
                print(f'Training Report / Iteration {iteration} / Time Per Iteration: {(time() - start_time) / self.train_report_freq:.2f}s / Mean Q_max: {np.mean(Q_values):.2f} / Mean Loss: {np.mean(losses):.5f}')
                Q_values = []
                losses = []
                start_time = time()

            # Store the weights of the model after [model_save_freq] iterations
            if not iteration % self.model_save_freq:
                self.agent.save_model()

            # Save the experiences from the replay buffer after [update_experience_freq] iterations
            if not iteration % self.memory_update_freq:
                self.agent.memory.save()
