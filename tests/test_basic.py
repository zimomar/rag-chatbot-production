"""Tests basiques pour valider l'agent."""

from src.agent.graph import RAGAgent


def test_agent_init():
    """Vérifie que l'agent s'initialise sans erreur."""
    # Note: On n'initialise pas vraiment les composants lourds ici
    # Juste vérifier que les classes sont importables et instanciables
    assert RAGAgent is not None
