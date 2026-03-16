from pydantic import BaseModel


class IdFormatConfig(BaseModel):
    prefix: str = "REC"
    format: str = "{prefix}-{YYYYMM}-{rand:04d}"


class WorkflowState(BaseModel):
    id: str
    label: str
    color: str = "secondary"


class CollectionWorkflow(BaseModel):
    initial_state: str = "new"
    states: list[WorkflowState] = [
        WorkflowState(id="new",         label="New",         color="secondary"),
        WorkflowState(id="open",        label="Open",        color="primary"),
        WorkflowState(id="in_progress", label="In Progress", color="warning"),
        WorkflowState(id="on_hold",     label="On Hold",     color="info"),
        WorkflowState(id="closed",      label="Closed",      color="success"),
    ]


class ListColumn(BaseModel):
    key: str
    label: str


class CollectionRole(BaseModel):
    id: str
    label: str = ""


class TakeOverConfig(BaseModel):
    """Configuration for the Take Over button on the record detail page.

    field      – key of the field (in any section) that will receive the new value
    value_type – what to write into the field:
                   "username"  → current logged-in user's username (default)
                   "timestamp" → current UTC ISO-8601 timestamp
                 Future extensions: "group", "ldap_user", etc.
    """
    field: str
    value_type: str = "username"


class CollectionConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    terminology: dict[str, str] = {}
    workflow: CollectionWorkflow = CollectionWorkflow()
    list_columns: list[ListColumn] = [
        ListColumn(key="record_owner", label="Record Owner"),
    ]
    id_format: IdFormatConfig = IdFormatConfig()
    roles: list[CollectionRole] = [
        CollectionRole(id="collection_admin", label="Collection Admin"),
        CollectionRole(id="collection_user",  label="Collection User"),
    ]
    # Field key used as the human-readable record title in the detail page header.
    # Searched across all sections (including nested section_groups).
    # If None or the field is not found, falls back to template_name.
    title_field: str | None = None
    # When set, the "Take Over" button is shown on the record detail page.
    # When None, the button is hidden entirely.
    take_over: TakeOverConfig | None = None
