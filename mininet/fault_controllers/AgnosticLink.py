"""Having this in link.py leads to circular imports"""

class AgnosticLink:
    """This class contains all information that is required to run a command effecting this link via both its interfaces
    without having access to the corresponding node. It is used by FaultControllers, which run in a different process."""

    def __init__(self, link1_pid, link1_name, link1_node_name,
                 link2_pid, link2_name, link2_node_name):

        self.link1_pid = link1_pid
        self.link1_name = link1_name
        self.link1_node_name = link1_node_name
        self.link2_pid = link2_pid
        self.link2_name = link2_name
        self.link2_node_name = link2_node_name
        self.traffic = 0


    def __eq__(self, other):
        if not isinstance(other, AgnosticLink):
            return False
        if {self.link1_pid, self.link2_pid} != {other.link1_pid, other.link2_pid}:
            return False
        if {self.link1_name, self.link2_name} != {other.link1_name, other.link2_name}:
            return False
        return True

    def __hash__(self):
        return hash((self.link1_pid, self.link1_name, self.link1_node_name, self.link2_pid, self.link2_name, self.link2_node_name))
