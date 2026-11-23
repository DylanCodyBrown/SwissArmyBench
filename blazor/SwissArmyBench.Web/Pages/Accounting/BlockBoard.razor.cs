using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api.Accounting;

namespace SwissArmyBench.Web.Pages.Accounting;

public partial class BlockBoard
{
    // A cell's size on the board, and the letters' and numbers' heads (the classic COL_W, ROW_H, HEAD_W, HEAD_H).
    private const int ColW = 76;
    private const int RowH = 24;
    private const int HeadW = 40;
    private const int HeadH = 22;

    // The board shows at least this many columns and rows, and this many beyond the last block.
    private const int MinColumns = 18;
    private const int MinRows = 36;
    private const int MoreColumns = 3;
    private const int MoreRows = 6;

    // A press moves a block once the pointer went this far (pixels).
    private const int DragThreshold = 5;

    private ElementReference _board;
    private BlockDrag? _drag;
    private IJSObjectReference? _module;
    private string? _focusAfter;

    [Parameter, EditorRequired]
    public WorkbookSheet Sheet { get; set; } = default!;

    [Parameter]
    public string? Selected { get; set; }

    [Parameter]
    public EventCallback<string?> OnSelect { get; set; }

    [Parameter]
    public Func<string, IReadOnlyDictionary<string, object?>, Task<WorkbookState?>> OnPatch { get; set; } = default!;

    [Parameter]
    public EventCallback<string> OnRemove { get; set; }

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    private int Right => Sheet.Blocks.Select(b => WorkbookRules.CellAt(b.Cell).Column + b.W + MoreColumns).Append(MinColumns).Max();

    private int Bottom => Sheet.Blocks.Select(b => WorkbookRules.CellAt(b.Cell).Row + b.H + MoreRows).Append(MinRows).Max();

    private int Width => HeadW + (Right * ColW);

    private int Height => HeadH + (Bottom * RowH);

    private string CellsStyle => Invariant($"width: {Width}px; height: {Height}px; --col: {ColW}px; --row: {RowH}px");

    private static string Px(string a, double x, string b, double y) => Invariant($"{a}: {x}px; {b}: {y}px");

    private static string BlockStyle(int row, int column, int w, int h) =>
        Invariant($"left: {HeadW + ((column - 1) * ColW)}px; top: {HeadH + ((row - 1) * RowH)}px; width: {(w * ColW) - 2}px; height: {(h * RowH) - 2}px");

    private static string Invariant(FormattableString text) => text.ToString(CultureInfo.InvariantCulture);

    /// <summary>Where a block shows: where it is, or where the drag has it now.</summary>
    private (int Row, int Column, int W, int H) Shown(WorkbookBlock block)
    {
        if (_drag is { } d && d.Id == block.Id)
        {
            return (d.Row, d.Column, d.W, d.H);
        }
        var (row, column) = WorkbookRules.CellAt(block.Cell);
        return (row, column, block.W, block.H);
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (_focusAfter is { } id)
        {
            _focusAfter = null;
            await (await ModuleAsync()).InvokeVoidAsync("focusBlock", _board, id);
        }
    }

    private async Task<IJSObjectReference> ModuleAsync() =>
        _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/workbook.js");

    private async Task BoardDownAsync()
    {
        if (Selected is not null)
        {
            await OnSelect.InvokeAsync(null);
        }
    }

    private async Task BlockDownAsync(PointerEventArgs e, WorkbookBlock block, bool sizing)
    {
        if (e.Button != 0)
        {
            return;
        }
        if (!sizing)
        {
            await OnSelect.InvokeAsync(block.Id);
        }
        var (row, column) = WorkbookRules.CellAt(block.Cell);
        _drag = new BlockDrag(block.Id, sizing, e.ClientX, e.ClientY, row, column, block.W, block.H);
        await (await ModuleAsync()).InvokeVoidAsync("capture", _board, e.PointerId);
    }

    private void Move(PointerEventArgs e)
    {
        if (_drag is not { } d || Sheet.Blocks.FirstOrDefault(b => b.Id == d.Id) is not { } block)
        {
            return;
        }
        var (dx, dy) = (e.ClientX - d.StartX, e.ClientY - d.StartY);
        if (!d.Moved && Math.Abs(dx) + Math.Abs(dy) < DragThreshold)
        {
            return;
        }
        var (row, column) = WorkbookRules.CellAt(block.Cell);
        _drag = d.Sizing
            ? d with { Moved = true, W = Math.Max(1, (int)Math.Round(((block.W * ColW) + dx) / ColW)), H = Math.Max(1, (int)Math.Round(((block.H * RowH) + dy) / RowH)) }
            : d with { Moved = true, Column = Math.Max(1, column + (int)Math.Round(dx / ColW)), Row = Math.Max(1, row + (int)Math.Round(dy / RowH)) };
    }

    private async Task UpAsync(PointerEventArgs e)
    {
        if (_drag is not { Moved: true } d || Sheet.Blocks.FirstOrDefault(b => b.Id == d.Id) is not { } block)
        {
            _drag = null;
            return;
        }
        var cell = WorkbookRules.Address(d.Row, d.Column);
        if (d.Sizing && (d.W != block.W || d.H != block.H))
        {
            await OnPatch(block.Id, new Dictionary<string, object?> { ["w"] = d.W, ["h"] = d.H });
        }
        else if (!d.Sizing && cell != block.Cell)
        {
            await OnPatch(block.Id, new Dictionary<string, object?> { ["cell"] = cell });
        }
        _drag = null;
    }

    private async Task BlockKeyAsync(KeyboardEventArgs e, WorkbookBlock block)
    {
        var (row, column) = WorkbookRules.CellAt(block.Cell);
        var (dr, dc) = e.Key switch
        {
            "ArrowLeft" => (0, -1),
            "ArrowRight" => (0, 1),
            "ArrowUp" => (-1, 0),
            "ArrowDown" => (1, 0),
            _ => (0, 0),
        };
        if (dr != 0 || dc != 0)
        {
            if (row + dr >= 1 && column + dc >= 1)
            {
                _focusAfter = block.Id;
                await OnPatch(block.Id, new Dictionary<string, object?> { ["cell"] = WorkbookRules.Address(row + dr, column + dc) });
            }
        }
        else if (e.Key is "Delete" or "Backspace")
        {
            await OnRemove.InvokeAsync(block.Id);
        }
        else if (e.Key is "Enter" or " ")
        {
            await OnSelect.InvokeAsync(block.Id);
        }
    }

    private async Task GripKeyAsync(KeyboardEventArgs e, WorkbookBlock block)
    {
        var (dw, dh) = e.Key switch
        {
            "ArrowRight" => (1, 0),
            "ArrowLeft" => (-1, 0),
            "ArrowDown" => (0, 1),
            "ArrowUp" => (0, -1),
            _ => (0, 0),
        };
        if (dw != 0 || dh != 0)
        {
            await OnPatch(block.Id, new Dictionary<string, object?> { ["w"] = Math.Max(1, block.W + dw), ["h"] = Math.Max(1, block.H + dh) });
        }
    }
}
