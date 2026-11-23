using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.Pages.Grids.Cards;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>A cell's whole value (the classic valueViewer.ts: a double-click, Enter or F2 on a cell, the menu's View
/// value), a column's profile, and what the grid page sends to the Analyze board by hand (the classic cellMenu.ts:
/// a value, a row, a column's profile, its distinct values, the whole view's profile).</summary>
public partial class GridsPage
{
    private const string ViewValue = "view-value";
    private const string ColumnProfile = "column-profile";

    private (string Title, JsonElement Value)? _viewing;
    private string? _profileColumn;

    private async Task ViewCellAsync(GridPoint at)
    {
        if (_grid is null)
        {
            return;
        }
        var value = await _grid.CellAsync(at.Row, at.Column);
        _viewing = ($"{at.Column}, row {at.Row + 1:N0}", value);
        _dialog = ViewValue;
        StateHasChanged();
    }

    private void OpenProfile(string column)
    {
        _profileColumn = column;
        _dialog = ColumnProfile;
    }

    private async Task FilterFromProfileAsync(object step)
    {
        await AddStepAsync(("filter", step));
        if (_error is null)
        {
            var column = JsonSerializer.SerializeToElement(step, ApiClient.Json).GetProperty("column").GetString();
            _ = Notes.SayAsync($"Added a filter step on {column}.");
        }
    }

    /// <summary>Each card to the board (POST /grids/{id}/cards), then one line saying what arrived.</summary>
    private async Task SendCardsAsync(IReadOnlyList<BoardCard> cards)
    {
        if (_active is not { } grid)
        {
            return;
        }
        try
        {
            foreach (var card in cards)
            {
                await Api.PostAsync($"/grids/{ApiClient.Part(grid)}/cards", card);
            }
            _ = Notes.SayAsync($"On the Analyze board: {(cards.Count == 1 ? "a note" : "a note and its chart")}.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SendValueAsync(GridPoint at, string where)
    {
        if (_grid is not null && _info is { } info)
        {
            await SendCardsAsync(GridCards.Value(await _grid.CellAsync(at.Row, at.Column), where, info.Dataset));
        }
    }

    private async Task SendRowAsync(long row)
    {
        if (_grid is not null && _info is { } info)
        {
            await SendCardsAsync(GridCards.Row(await _grid.RowValuesAsync(row), row, info.Dataset));
        }
    }

    /// <summary>A column's profile on the board: its numbers, its most common values, its chart.</summary>
    private async Task ProfileToAnalyzeAsync(string column)
    {
        if (_info is not { } info)
        {
            return;
        }
        try
        {
            await SendCardsAsync(ProfileCards.Column(await Grids.ProfileAsync(info.Grid, column, _previewUpto), info.Dataset));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A column's values and how often each shows up: the Analyze page's own count (the odds analysis with no
    /// outcome), so its cards are the ones Analyze makes.</summary>
    private async Task DistinctToAnalyzeAsync(string column)
    {
        try
        {
            await Api.PostAsync("/analyze/run", new { analysis = "odds", table = _active, columns = new { column, outcome = string.Empty } });
            _ = Notes.SayAsync("On the Analyze board: a note and its chart.");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A LIST or STRUCT column unnested: a SQL step the server writes.</summary>
    private Task UnnestAsync(string column) =>
        ChangedAsync(() => Api.PostAsync<Api.Grids.GridInfo>($"/grids/{ApiClient.Part(_active!)}/unnest", new { column }));
}
