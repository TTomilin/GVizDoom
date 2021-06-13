#!/usr/bin/env python
from __future__ import print_function

import random
import time
import numpy as np
from collections import deque
from threading import get_ident

from .agent import Agent
from .scenario import Scenario
from .stats_writer import Statistics
from .util import new_episode, idx_to_action


class Doom:
    def __init__(self, agent: Agent, scenario: Scenario, stats_save_freq: int, max_epochs: int,
                 KPI_update_freq: int, append_statistics: bool, train: bool, seed: bool, n_steps: int):
        self.seed = seed
        self.train = train
        self.agent = agent
        self.n_steps = n_steps
        self.scenario = scenario
        self.max_epochs = max_epochs
        self.stats_save_freq = stats_save_freq
        self.KPI_update_freq = KPI_update_freq
        self.append_statistics = append_statistics

    def play(self) -> None:
        """ Main RL loop of the game """

        train = self.train
        agent = self.agent
        scenario = self.scenario
        task_id = scenario.task
        print(f'Running {type(agent).__name__} on {scenario.name}, task {task_id}, thread {get_ident()}')

        game = scenario.game
        game.init()
        game.new_episode()
        game_state = game.get_state()

        # Store a fixed length of most recent variables from the game
        game_variables = deque(maxlen = scenario.variable_history_size)
        game_variables.append(game_state.game_variables)

        # Store a fixed length of most recent transitions for multi-step updates
        transitions = deque(maxlen = self.n_steps)

        spawn_point_counter = {}
    
        # Create statistics manager
        statistics = Statistics(agent, scenario, self.stats_save_freq, self.KPI_update_freq, self.append_statistics)
    
        # Statistic counters
        time_step, n_game, total_reward, frames_alive, total_duration = 0, 0, 0, 0, 0
        start_time = time.time()
    
        current_state = agent.transform_initial_state(game.get_state())

        # Initial normalized measurements for Direct Future Prediction (DFP)
        measurements = scenario.get_measurements(game_variables, False)

        while n_game < self.max_epochs:

            action_idx = agent.get_action(current_state, measurements)
            game.set_action(idx_to_action(action_idx, agent.action_size))
            game.advance_action(agent.frames_per_action)
            terminated = game.is_episode_finished()
            reward = game.get_last_reward()
    
            if terminated:
                n_game += 1
                duration = time.time() - start_time
                total_duration += duration
    
                # Append statistics
                statistics.append_episode(n_game, time_step, frames_alive, duration, total_reward, game_variables)

                # Reset counters and game variables
                frames_alive, total_reward = 0, 0
                start_time = time.time()
                game_variables.clear()

                # Run a new episode. Use a fixed seed if it is provided, otherwise ensure randomness
                game.set_seed(self.seed if self.seed else np.random.randint(10000))
                game.new_episode() if self.seed else new_episode(game, spawn_point_counter, scenario.n_spawn_points)
            else:
                frames_alive += 1

            # Acquire and transform the new state of the game
            new_state = game.get_state()
            game_variables.append(new_state.game_variables)
            new_state = agent.transform_new_state(current_state, new_state)

            # Shape the reward
            reward = scenario.shape_reward(reward, game_variables)
            total_reward += reward
            time_step += 1
    
            if train:
                # Store the transition <s, a, r, s', t> in the experience replay buffer
                transitions.append((current_state, action_idx, reward, new_state, measurements, terminated, task_id))
                if not frames_alive % self.n_steps and frames_alive != 0:
                    agent.memory.add(np.array(transitions))
                # Calculate the normalized measurements for Direct Future Prediction (DFP)
                measurements = scenario.get_measurements(game_variables, terminated)
    
            current_state = new_state

            # Save agent's performance statistics
            if not time_step % statistics.save_frequency:
                statistics.write(n_game, total_duration)
    
        # Write the final statistics at the end of the last epoch
        statistics.write(n_game, total_duration)
