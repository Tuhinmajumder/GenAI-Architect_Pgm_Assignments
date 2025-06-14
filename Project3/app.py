import streamlit as st
import atexit
from authorization.authorization import retrive_credential
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.trace.samplers import AlwaysOnSampler
from opencensus.trace.tracer import Tracer
from opencensus.ext.azure import metrics_exporter
from frontend.functions import validate_environment, AppInitializer, display_sidebar_info, display_ticket_form, process_and_display_ticket, cleanup_resources

# Initialize Application Insights
def initialize_telemetry():
    connection_string = retrive_credential("APPLICATIONINSIGHTS-CONNECTION-STRING")
    if not connection_string:
        st.warning("Application Insights connection string not found. Telemetry will not be enabled.")
        return None
    
    # Set up tracer for Application Insights
    tracer = Tracer(
        exporter=AzureExporter(connection_string=connection_string),
        sampler=AlwaysOnSampler()
    )
    
    # Set up metrics exporter
    metrics = metrics_exporter.MetricsExporter(connection_string=connection_string)
    
    return tracer, metrics

# Flush telemetry on exit
def flush_telemetry():
    if "tracer" in st.session_state and st.session_state.tracer:
        st.session_state.tracer.exporter.flush()
    if "metrics" in st.session_state and st.session_state.metrics:
        st.session_state.metrics.flush()

def main():
    """
    Main application function that orchestrates the complete Streamlit ticket system.
    
    Handles application configuration, system initialization, user interface creation,
    and the complete ticket processing workflow. Provides comprehensive error handling
    and user guidance for system setup and troubleshooting. Integrates Application Insights
    for telemetry tracking.
    
    Raises:
        RuntimeError: If critical system initialization failures occur that prevent
                     the application from functioning, though the function attempts
                     to provide helpful troubleshooting guidance to users.
    """
    
    # Initialize Application Insights telemetry
    telemetry = initialize_telemetry()
    if telemetry:
        st.session_state.tracer, st.session_state.metrics = telemetry
        with st.session_state.tracer.span(name="Main Page Load"):
            st.session_state.tracer.add_attribute_to_current_span(
                attribute_key="page",
                attribute_value="Smart Ticket System"
            )
    
    st.set_page_config(
        page_title="Smart Ticket System",
        page_icon="🎫",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🎫 Smart Ticket Resolution System")
    st.markdown("*AI-powered ticket processing with Azure AI Search integration*")
    
    if not validate_environment():
        if "tracer" in st.session_state and st.session_state.tracer:
            with st.session_state.tracer.span(name="Environment Validation Failed"):
                st.session_state.tracer.add_attribute_to_current_span(
                    attribute_key="error",
                    attribute_value="Environment validation failed"
                )
        st.stop()
    
    if "system_ready" not in st.session_state:
        with st.container():
            try:
                with st.session_state.tracer.span(name="System Initialization") if "tracer" in st.session_state else st.empty():
                    st.session_state.system_components = AppInitializer.initialize_system()
                    st.session_state.system_ready = st.session_state.system_components is not None
            except Exception as e:
                st.session_state.system_ready = False
                if "tracer" in st.session_state and st.session_state.tracer:
                    with st.session_state.tracer.span(name="System Initialization Error"):
                        st.session_state.tracer.add_attribute_to_current_span(
                            attribute_key="error",
                            attribute_value=str(e)
                        )
                st.error(f"System initialization failed: {e}")
    
    if not st.session_state.system_ready:
        st.error("⚠️ System initialization failed. Please check your configuration and try again.")
        st.stop()
    
    data_manager, active_vsm, processor = st.session_state.system_components
    
    display_sidebar_info()
    
    locationID, description = display_ticket_form()
    
    if locationID is not None and description:
        if not description.strip():
            st.error("❌ Please provide a description of your issue.")
        elif len(description.strip()) < 20:
            st.error("❌ Please provide more details about your issue (at least 20 characters).")
        else:
            try:
                with st.session_state.tracer.span(name="Ticket Processing") if "tracer" in st.session_state else st.empty():
                    process_and_display_ticket(processor, active_vsm, locationID, description.strip())
                    if "tracer" in st.session_state and st.session_state.tracer:
                        st.session_state.tracer.add_attribute_to_current_span(
                            attribute_key="ticket_submitted",
                            attribute_value=f"LocationID: {locationID}"
                        )
            except Exception as e:
                if "tracer" in st.session_state and st.session_state.tracer:
                    with st.session_state.tracer.span(name="Ticket Processing Error"):
                        st.session_state.tracer.add_attribute_to_current_span(
                            attribute_key="error",
                            attribute_value=str(e)
                        )
                st.error(f"❌ Failed to process ticket: {e}")
    
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #666; padding: 20px;'>"
        "Smart Ticket System | Powered by Azure AI Search, Blob Storage and Weaviate"
        "</div>", 
        unsafe_allow_html=True
    )

# Register cleanup and telemetry flush on exit
atexit.register(cleanup_resources)
atexit.register(flush_telemetry)

if __name__ == "__main__":
    main()