"""
Chart rendering.
"""
import contextlib
import io
import streamlit as st
import matplotlib.pyplot as plt


class ChartRenderer:
    """Handles chart rendering from generated code."""

    def render_from_code(self, code_block, explanation=None):
        """
        Execute chart code.

        Args:
            code_block: chart code string
            explanation: optional explanation text to display above chart
        """
        if not code_block:
            st.info("No chart code was generated in the response.")
            return

        st.subheader("📊 Chart")
        
        if explanation:
            st.markdown(explanation)

        try:
            # Reset matplotlib state
            plt.close("all")

            # Prevent premature closing of figures
            code_block = code_block.replace("\nplt.close()", "")

            # Execute in a shared namespace (like map_renderer) so we can capture `fig`
            exec_globals = {"plt": plt}

            with contextlib.redirect_stdout(io.StringIO()):
                exec(code_block, exec_globals, exec_globals)

            # Prefer explicit `fig` from executed code, otherwise fall back to plt.gcf()
            fig = exec_globals.get("fig")
            if fig is None:
                fig = plt.gcf()

            if fig and fig.get_axes():
                st.pyplot(fig)
                plt.close(fig)
            else:
                st.warning(
                    "No chart was generated. The code ran, but no figure was created."
                )

        except Exception as e:
            st.error(f"Error running chart code: {e}")
