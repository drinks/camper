from django.template import NodeList, engines


# This monkeypatches django.template's NodeList with a flatten method
# to recursively collect a list of nodes down a template's `extends` chain
def flatten(self):
    nodes = []
    for node in self:
        nodes.append(node)
        if hasattr(node, 'nodelist'):
            nodes.extend(node.nodelist.flatten())
    return nodes

NodeList.flatten = flatten


def get_template_from_string(str):
    return engines['django'].from_string(str)
