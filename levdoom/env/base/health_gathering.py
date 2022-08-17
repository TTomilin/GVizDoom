from argparse import Namespace

from levdoom.env.base.scenario import DoomEnv


class HealthGathering(DoomEnv):
    """
    In this scenario, the agent is trapped in a room with a surface, which slowly but constantly decreases the agent’s
    health. Health granting items continually spawn in random locations at specified time intervals. The default health
    item heals grants 25 hit points. Some environments contain poison vials, which inflict damage to the agent instead
    of providing health. The objective is to survive. The agent should identify the health granting items and navigate
    around the map to collect them quickly enough to avoid running out of health. The agent can turn left and right,
    and move forward. A small reward is granted for every frame the agent manages to survive.
    """

    def __init__(self, args: Namespace, task: str, frame_survived_reward=0.01):
        self.add_speed = args.add_speed
        self.reward_frame_survived = frame_survived_reward
        super().__init__(args, task)

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

    def calc_reward(self) -> float:
        return self.reward_frame_survived
