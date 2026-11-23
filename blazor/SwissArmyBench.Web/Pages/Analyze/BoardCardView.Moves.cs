using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Analyze;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Analyze;

// A card's own moves on the board (the classic aiPanel.ts cardElement, resizeGrip and makeMovable): Pin to the top,
// its "…" (Edit note, Move earlier, Move later, Start a new page here), its size by the corner grip (drag, or the
// arrow keys: left and right the width, up and down the height; a double-click its kind's size), and its place by
// dragging its head. Each is kept on the server (PATCH /cards/{id}), so Page view, the PDF and a dashboard see it.
public partial class BoardCardView
{
    // The board's measures (the classic aiPanel.ts): a row's height and the gap between cards, in pixels.
    private const int GapPixels = 12;
    private const int MinWidth = 2;
    private const int MinHeight = 3;
    private const int MaxHeight = 30;

    private ElementReference _head;
    private ElementReference _grip;
    private IJSObjectReference? _board;
    private DotNetObjectReference<BoardCardView>? _self;
    private MenuOpen? _menu;

    [Inject]
    private BoardClient Board { get; set; } = default!;

    /// <summary>The card before this one on the board (Move earlier goes before it), or null.</summary>
    [Parameter]
    public string? Previous { get; set; }

    /// <summary>The card two after this one (Move later goes before it; null: to the end), and whether one follows.</summary>
    [Parameter]
    public (bool Any, string? Before) Later { get; set; }

    /// <summary>The card changed on the server: the board reads its cards again.</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    [Parameter]
    public EventCallback<BoardCard> OnEditNote { get; set; }

    private string Name => Card.Title.Length > 0 ? Card.Title : KindName;

    private string KindName => Card.Kind switch
    {
        "chart" => "Chart",
        "note" => "Note",
        "table" => "Result",
        "diagram" => "Diagram",
        "plotly" => "Plotly figure",
        "vegalite" => "Vega-Lite chart",
        "image" => "Image",
        _ => Card.Kind,
    };

    private bool Sized => Card.Size is { ValueKind: JsonValueKind.Object };

    private int Width => Math.Clamp(Size("w", DefaultWidth), MinWidth, BoardColumns);

    private int Height => Math.Clamp(Size("h", DefaultHeight), MinHeight, MaxHeight);

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            _self = DotNetObjectReference.Create(this);
            _board = await Js.InvokeAsync<IJSObjectReference>("import", "./js/board.js");
            await _board.InvokeVoidAsync("grip", _grip, _self, RowUnitPixels, GapPixels);
            await _board.InvokeVoidAsync("movable", _head, _self);
        }
    }

    private Task PatchAsync(Dictionary<string, object?> change) => DoAsync(async () =>
    {
        await Board.PatchAsync(Card.Id, change);
        await OnChanged.InvokeAsync();
    });

    private Task TogglePinAsync() => PatchAsync(new() { ["pinned"] = !Card.Pinned });

    /// <summary>A double-click on the grip: back to the kind's size.</summary>
    private Task FitAsync() => PatchAsync(new() { ["size"] = null });

    private Task SizeAsync(int w, int h) =>
        PatchAsync(new() { ["size"] = new { w = Math.Clamp(w, MinWidth, BoardColumns), h = Math.Clamp(h, MinHeight, MaxHeight) } });

    [JSInvokable]
    public Task Resized(int w, int h) => InvokeAsync(() => SizeAsync(w, h));

    [JSInvokable]
    public Task Moved(string before) => InvokeAsync(() => PatchAsync(new() { ["before"] = before.Length == 0 ? null : before }));

    private Task GripKeyAsync(KeyboardEventArgs e) => e.Key switch
    {
        "ArrowLeft" => SizeAsync(Width - 1, Height),
        "ArrowRight" => SizeAsync(Width + 1, Height),
        "ArrowUp" => SizeAsync(Width, Height - 1),
        "ArrowDown" => SizeAsync(Width, Height + 1),
        _ => Task.CompletedTask,
    };

    private void ShowMenu(MouseEventArgs at)
    {
        List<MenuEntry> entries = [];
        if (Card.Kind == "note")
        {
            entries.Add(new("Edit note", "edit", () => OnEditNote.InvokeAsync(Card)));
        }
        if (Previous is { } previous)
        {
            entries.Add(new("Move earlier", "up", () => PatchAsync(new() { ["before"] = previous })));
        }
        if (Later.Any)
        {
            entries.Add(new("Move later", "down", () => PatchAsync(new() { ["before"] = Later.Before })));
        }
        entries.Add(new(Card.NewPage ? "Don't start a new page" : "Start a new page here", "rows", () => PatchAsync(new() { ["new_page"] = !Card.NewPage })));
        _menu = new MenuOpen(entries, at.ClientX, at.ClientY + 4);
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (_board is not null)
            {
                await _board.DisposeAsync();
            }
        }
        catch (JSDisconnectedException)
        {
            // the page is going
        }
        _self?.Dispose();
    }
}
