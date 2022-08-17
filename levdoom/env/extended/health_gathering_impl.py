from argparse import Namespace
from typing import Dict

from levdoom.env.base.health_gathering import HealthGathering


class HealthGatheringImpl(HealthGathering):

    def __init__(self, args: Namespace, task: str):
        super().__init__(args, task)
        self.health_acquired_reward = args.health_acquired_reward
        self.kits_obtained = 0

    def calc_reward(self) -> float:
        reward = super().calc_reward()
        current_vars = self.game_variable_buffer[-1]
        previous_vars = self.game_variable_buffer[-2]
        if current_vars[0] > previous_vars[0]:
            reward += self.health_acquired_reward  # Picked up health kit
            self.kits_obtained += 1
        return reward

    def get_statistics(self) -> Dict[str, float]:
        return {'kits_obtained': self.kits_obtained}

    def clear_episode_statistics(self):
        self.kits_obtained = 0

    def get_available_actions(self):
        actions = []
        speed = [[0.0], [1.0]]
        m_forward = [[0.0], [1.0]]
        t_left_right = [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0]]
        for m in m_forward:
            for t in t_left_right:
                if self.add_speed:
                    for s in speed:
                        actions.append(t + m + s)
                else:
                    actions.append(t + m)
        return actions
