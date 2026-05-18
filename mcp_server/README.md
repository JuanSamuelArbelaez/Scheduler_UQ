# MCP Calendar Server

A Model Context Protocol (MCP) server that provides JSON-RPC access to Google Calendar operations via HTTP.

## Overview

The MCP Calendar Server exposes Google Calendar create, update, and delete operations through a standard HTTP/JSON-RPC interface. It can be used to synchronize Scheduler UQ events with a Google Calendar account.

## Features

- **JSON-RPC 2.0 Protocol**: Standard request/response format
- **HTTP/1.1 Interface**: Simple POST-based communication at `/mcp` endpoint
- **Mock Mode**: Works without Google credentials for testing
- **Real Google Calendar Sync**: Production support with service account credentials
- **Tool Discovery**: Exposes `tools/list`, `prompts/list`, `resources/list` methods
- **Event Management**: Create, update, and delete calendar events

## Installation

### Requirements

- Python 3.13+
- Google Cloud SDK (optional, for real Google Calendar sync)

### Setup

```bash
pip install -r mcp_server/requirements.txt
```

## Running the Server

### Mock Mode (Testing)

```bash
python mcp_server/run.py
```

The server will start on `http://localhost:8088/mcp` in mock mode, where all operations succeed locally without real Google Calendar access.

### Production Mode (Real Google Calendar)

1. Create a Google Cloud service account and download the JSON credentials
2. Set the environment variable:

```bash
export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
export MCP_PORT=8088
python mcp_server/run.py
```

Or pass via command line:

```bash
python mcp_server/server.py 8088 /path/to/service-account.json
```

## API Reference

### Base URL

```
http://localhost:8088/mcp
```

### Request Format

All requests must be JSON-RPC 2.0:

```json
{
  "jsonrpc": "2.0",
  "method": "method_name",
  "params": { /* optional parameters */ },
  "id": 1
}
```

### Methods

#### `tools/list`

List available calendar tools.

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/list",
  "id": 1
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {
        "name": "google_calendar.create_event",
        "description": "Create a new Google Calendar event",
        "inputSchema": { /* JSON Schema */ }
      },
      /* ... more tools ... */
    ]
  },
  "id": 1
}
```

#### `prompts/list`

List available prompt templates.

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "prompts": [
      {
        "name": "calendar-event-template",
        "description": "Template for creating calendar events"
      }
    ]
  },
  "id": 1
}
```

#### `resources/list`

List available resources (calendars).

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "resources": [
      {
        "uri": "google-calendar://primary",
        "name": "Primary Calendar",
        "description": "User's primary Google Calendar"
      }
    ]
  },
  "id": 1
}
```

#### `tools/call`

Execute a calendar tool.

**Request (Create Event):**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "google_calendar.create_event",
    "arguments": {
      "calendar_id": "user@gmail.com",
      "title": "Meeting",
      "start_time_utc": "2026-05-20T14:00:00Z",
      "end_time_utc": "2026-05-20T15:00:00Z",
      "description": "Optional description",
      "location": "Optional location"
    }
  },
  "id": 2
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [{"type": "text", "text": "Event created: abc123"}],
    "external_id": "abc123"
  },
  "id": 2
}
```

**Request (Update Event):**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "google_calendar.update_event",
    "arguments": {
      "calendar_id": "user@gmail.com",
      "event_id": "abc123",
      "title": "Updated Meeting",
      "start_time_utc": "2026-05-20T15:00:00Z",
      "end_time_utc": "2026-05-20T16:00:00Z"
    }
  },
  "id": 3
}
```

**Request (Delete Event):**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "google_calendar.delete_event",
    "arguments": {
      "calendar_id": "user@gmail.com",
      "event_id": "abc123"
    }
  },
  "id": 4
}
```

## Testing

### Unit Tests

```bash
python mcp_server/test_server.py -v
```

### Integration Tests

```bash
python mcp_server/test_integration.py -v
```

Run all tests:

```bash
python -m pytest mcp_server/ -v
```

## Error Handling

The server returns JSON-RPC error responses for invalid requests:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found: unknown/method"
  },
  "id": 1
}
```

Error codes follow the JSON-RPC 2.0 specification:
- `-32700`: Parse error
- `-32601`: Method not found
- `-32603`: Internal error

## Integration with Scheduler UQ

The MCP server is designed to work with Scheduler UQ bot:

1. Configure in `.env`:
```
MCP_ENABLED=true
MCP_HTTP_ENDPOINT=http://localhost:8088/mcp
```

2. Start the MCP server:
```bash
python mcp_server/run.py
```

3. Start the Scheduler UQ bot:
```bash
python main.py
```

When events are created/updated/deleted in Telegram, they will be automatically synchronized with Google Calendar.

## Architecture

- **GoogleCalendarService**: Handles actual Google Calendar API interactions or mock operations
- **MCPRPCRouter**: Routes incoming JSON-RPC method calls to appropriate handlers
- **MCPCalendarHandler**: HTTP request handler that processes POST requests at `/mcp`

## Mock vs Production Mode

### Mock Mode
- No Google credentials required
- Events are logged locally
- Perfect for testing and development
- All operations return success

### Production Mode
- Requires Google service account credentials
- Events are synced to real Google Calendar
- Production-ready for calendar synchronization

## Troubleshooting

### Server won't start

Check if port 8088 is available:
```bash
lsof -i :8088  # macOS/Linux
netstat -ano | findstr :8088  # Windows
```

### Events not syncing to Google Calendar

1. Verify `GOOGLE_SERVICE_ACCOUNT_FILE` is set correctly
2. Check service account has Calendar API scope enabled
3. Ensure calendar ID is correct (usually the email address)
4. Check server logs for detailed error messages

### Connection refused from Scheduler UQ

1. Ensure MCP server is running on the configured port
2. Verify `MCP_HTTP_ENDPOINT` in `.env` matches server address
3. Check firewall rules allow localhost connections

## Development

### Project Structure

```
mcp_server/
├── server.py              # Main server implementation
├── run.py                 # Server launcher
├── test_server.py         # Unit tests
├── test_integration.py    # Integration tests
├── requirements.txt       # Python dependencies
└── __init__.py            # Package init
```

### Adding New Tools

To add a new calendar tool:

1. Add method to `GoogleCalendarService`
2. Add tool definition in `MCPRPCRouter.handle_rpc_method` under `tools/list`
3. Add tool handler in `MCPRPCRouter` (e.g., `call_new_tool`)
4. Add test cases for the new tool

## License

Same as Scheduler UQ project.
