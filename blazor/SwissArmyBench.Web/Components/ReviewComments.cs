namespace SwissArmyBench.Web.Components;

/// <summary>
/// The review comments waiting on one open document (the owner, 2026-11-27: "highlight a part ... right click then
/// make a comment, then a send to agent button to send all comments ... then reset the file so no comments are
/// retained"). Memory only: nothing here is ever part of the document's text, so no Save can write one. Each of the
/// document's editors (one for a script, one a cell for a notebook) draws its own and tells where the edits moved
/// them; Changed tells the tab's count and the Review comments list.
/// </summary>
public sealed class ReviewComments
{
    private readonly List<ReviewComment> _items = [];
    private readonly Dictionary<string, IReviewSurface> _surfaces = [];
    private int _ids;

    public event Action? Changed;

    public int Count => _items.Count;

    /// <summary>"3 annotations", "1 annotation" (the word on screen, the owner 2026-11-27).</summary>
    public string CountWords => Count == 1 ? "1 annotation" : $"{Count} annotations";

    /// <summary>The comments in the document's order: its editors as `parts` names them (a notebook's cells from
    /// the top; none: as first commented), lines within each.</summary>
    public IReadOnlyList<ReviewComment> Ordered(IReadOnlyList<string>? parts = null)
    {
        var known = (parts ?? []).Concat(_items.Select(c => c.Part)).Distinct().ToList();
        return _items.OrderBy(c => known.IndexOf(c.Part)).ThenBy(c => c.Line).ThenBy(c => c.End).ThenBy(c => c.Id).ToList();
    }

    /// <summary>The comments one editor draws (as it is made again: a notebook read again in place).</summary>
    public IReadOnlyList<ReviewComment> Of(string part) => _items.Where(c => c.Part == part).ToList();

    public ReviewComment? Find(int id) => _items.FirstOrDefault(c => c.Id == id);

    public void Attach(string part, IReviewSurface surface) => _surfaces[part] = surface;

    public void Detach(string part, IReviewSurface surface)
    {
        if (_surfaces.TryGetValue(part, out var held) && ReferenceEquals(held, surface))
        {
            _surfaces.Remove(part);
        }
    }

    public bool Has(string part) => _surfaces.ContainsKey(part);

    /// <summary>A comment made at a place of an editor, drawn there.</summary>
    public async Task<ReviewComment> AddAsync(string part, ReviewPlace place, string text, bool byAgent = false)
    {
        var made = new ReviewComment(++_ids, part, text.Trim(), byAgent);
        made.Place(place);
        _items.Add(made);
        if (_surfaces.TryGetValue(part, out var surface))
        {
            await surface.DrawAsync(made);
        }
        Changed?.Invoke();
        return made;
    }

    /// <summary>A note on whole lines of an editor (the agent's way: it names lines, never a selection).</summary>
    public async Task<ReviewComment> AddLinesAsync(string part, int line, int end, string text, bool byAgent)
    {
        if (!_surfaces.TryGetValue(part, out var surface) || await surface.LinesAsync(line, end) is not { } place)
        {
            throw new InvalidOperationException(part.Length > 0 ? $"This document has no {part} to annotate." : "This document's code is not on screen to annotate.");
        }
        return await AddAsync(part, place, text, byAgent);
    }

    public async Task RewordAsync(int id, string text)
    {
        if (Find(id) is not { } found)
        {
            return;
        }
        found.Text = text.Trim();
        if (_surfaces.TryGetValue(found.Part, out var surface))
        {
            await surface.RewordAsync(found);
        }
        Changed?.Invoke();
    }

    public async Task RemoveAsync(int id)
    {
        if (Find(id) is not { } found)
        {
            return;
        }
        _items.Remove(found);
        if (_surfaces.TryGetValue(found.Part, out var surface))
        {
            await surface.EraseAsync(id);
        }
        Changed?.Invoke();
    }

    /// <summary>Every comment gone (sent, or cleared): the document's text was never touched.</summary>
    public async Task ClearAsync()
    {
        _items.Clear();
        foreach (var surface in _surfaces.Values.ToList())
        {
            await surface.EraseAllAsync();
        }
        Changed?.Invoke();
    }

    /// <summary>An editor says where its comments stand after an edit.</summary>
    public void Moved(IReadOnlyList<ReviewPlace> places)
    {
        var changed = false;
        foreach (var place in places)
        {
            if (Find(place.Id) is { } found && (found.Line != place.Line || found.End != place.End || found.Code != place.Code || found.Column != place.Column || found.EndColumn != place.EndColumn))
            {
                found.Place(place);
                changed = true;
            }
        }
        if (changed)
        {
            Changed?.Invoke();
        }
    }

    /// <summary>Every comment's place and code read from its editor as it is this moment (before a send).</summary>
    public async Task RefreshAsync()
    {
        foreach (var surface in _surfaces.Values.ToList())
        {
            Moved(await surface.PlacesAsync());
        }
    }

    public Task ShowAsync(int id) =>
        Find(id) is { } found && _surfaces.TryGetValue(found.Part, out var surface) ? surface.ShowAsync(id) : Task.CompletedTask;

    public Task EditAsync(int id) =>
        Find(id) is { } found && _surfaces.TryGetValue(found.Part, out var surface) ? surface.AskAsync(id) : Task.CompletedTask;

    /// <summary>The comment box opened for the selection of the editor that has `part` (the palette's Comment…).</summary>
    public Task AskAsync(string part) => _surfaces.TryGetValue(part, out var surface) ? surface.AskAsync(null) : Task.CompletedTask;
}
