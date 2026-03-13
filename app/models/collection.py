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


class CollectionConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    terminology: dict[str, str] = {}
    workflow: CollectionWorkflow = CollectionWorkflow()
    list_columns: list[ListColumn] = [
        ListColumn(key="coordinator", label="Coordinator"),
    ]
    id_format: IdFormatConfig = IdFormatConfig()
    roles: list[CollectionRole] = [
        CollectionRole(id="collection_admin", label="Collection Admin"),
        CollectionRole(id="collection_user",  label="Collection User"),
    ]
