using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;

namespace SwissArmyBench.Web.Pages.Apis;

/// <summary>Add API's preview (what it would write, asked as the form changes and written nowhere), Try it and Add.</summary>
public sealed partial class AddApiForm
{
    /// <summary>What the form sends, or nothing while it says too little to read.</summary>
    private Dictionary<string, object?>? Sent()
    {
        var sent = new Dictionary<string, object?>();
        if (_mode == "form")
        {
            var endpoints = _cards.Where(c => c.Path.Trim().Length > 0).Select(c => c.Sent()).ToList();
            if (endpoints.Count == 0 || _baseUrl.Trim().Length == 0)
            {
                return null;
            }
            sent["form"] = new Dictionary<string, object?>
            {
                ["title"] = _name.Trim().Length > 0 ? _name.Trim() : "API",
                ["base_url"] = _baseUrl.Trim(),
                ["endpoints"] = endpoints,
            };
        }
        else if (_mode == "document")
        {
            if (_file.Length > 0)
            {
                sent["spec_path"] = _file;
            }
            else if (_pasted.Trim().Length > 0)
            {
                sent["spec"] = _pasted;
            }
            else if (_url.Trim().Length > 0)
            {
                sent["spec_url"] = _url.Trim();
            }
            else
            {
                return null;
            }
            if (_baseUrl.Trim().Length > 0)
            {
                sent["base_url"] = _baseUrl.Trim();
            }
        }
        else
        {
            return null;
        }
        if (_named)
        {
            sent["name"] = _name.Trim();
        }
        if (_authTouched || _mode == "form")
        {
            sent["auth"] = _auth;
        }
        return sent;
    }

    /// <summary>The preview asked again once the typing pauses.</summary>
    private void Later(int pause = PreviewPauseMilliseconds)
    {
        _waiting?.Cancel();
        _waiting = new CancellationTokenSource();
        var token = _waiting.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(pause, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            await PreviewAsync();
            StateHasChanged();
        });
    }

    private async Task<AddApiPlan?> PreviewAsync()
    {
        var mine = ++_asked;
        if (Sent() is not { } sent)
        {
            _plan = null;
            return null;
        }
        _previewing = true;
        try
        {
            var got = await Apis.PreviewAsync(sent);
            if (mine != _asked)
            {
                return null;
            }
            _plan = got;
            _error = null;
            _said = null;
            if (!_named)
            {
                _name = got.Connection;
            }
            if (_mode == "document")
            {
                _documentAuth = AuthOf(got.Spec.Auth);
                if (!_authTouched)
                {
                    _auth = new(_documentAuth);
                }
                ChooseDefaultAuth();
            }
            return got;
        }
        catch (ApiException error) when (mine == _asked)
        {
            _plan = null;
            _error = error;
            return null;
        }
        finally
        {
            _previewing = false;
        }
    }

    /// <summary>The values typed for the variables the client reads (the first is the base address's own).</summary>
    private IReadOnlyList<PlanVariable> Asked => _plan?.Variables.Skip(1).ToList() ?? [];

    private Dictionary<string, string> Typed => Asked.Where(v => _values.GetValueOrDefault(v.Name) is { Length: > 0 }).ToDictionary(v => v.Name, v => _values[v.Name]);

    /// <summary>Try it: an operation's first rows (by its name, or a card's place among the endpoints), written nowhere.</summary>
    private async Task TryAsync(string key, int? card, string? operation)
    {
        _trying = key;
        _waiting?.Cancel();
        var fresh = await PreviewAsync();
        var name = operation ?? (card is { } at && fresh?.Spec.Operations.ElementAtOrDefault(at) is { } op ? op.Name : null);
        if (Sent() is not { } sent || name is null)
        {
            _trying = null;
            _tried = (key, null, new InvalidOperationException(_mode == "form" && _baseUrl.Trim().Length == 0 ? "Give the base address first." : "Fix the form first."));
            return;
        }
        sent["try"] = name;
        sent["values"] = Typed;
        try
        {
            _tried = (key, await Apis.TryAsync(sent), null);
        }
        catch (ApiException error)
        {
            _tried = (key, null, error);
        }
        _trying = null;
    }

    private Task TryCardAsync(EndpointCard card) =>
        TryAsync($"card:{_cards.IndexOf(card)}", _cards.Where(c => c.Path.Trim().Length > 0).ToList().IndexOf(card), null);

    /// <summary>Add: the files written; a value typed for Try it kept as the connection's (a secret in the keyring).</summary>
    private async Task AddAsync()
    {
        if (Sent() is not { } sent || _plan is null)
        {
            return;
        }
        var secrets = Asked.Where(v => v.Secret).Select(v => v.Name).ToHashSet();
        var typed = Typed;
        if (typed.Count > 0)
        {
            sent["variables"] = typed.Select(v => secrets.Contains(v.Key)
                ? new Dictionary<string, string> { ["name"] = v.Key, ["from"] = "keyring" }
                : new Dictionary<string, string> { ["name"] = v.Key, ["from"] = "value", ["value"] = v.Value }).ToList();
            sent["secrets"] = typed.Where(v => secrets.Contains(v.Key)).ToDictionary(v => v.Key, v => v.Value);
        }
        _adding = true;
        try
        {
            var done = await Apis.AddAsync(sent);
            _ = Notes.SayAsync($"Added {done.Connection}: {done.File}");
            await OnAdded.InvokeAsync(done.Saved?.Name ?? done.Connection);
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _adding = false;
    }

    private void RemoveCard(EndpointCard card)
    {
        _cards.Remove(card);
        Later();
    }

    private void ToggleNeeded(EndpointCard card, string name, bool on)
    {
        if (on)
        {
            card.Needed.Add(name);
        }
        else
        {
            card.Needed.Remove(name);
        }
        Later();
    }

    /// <summary>One of a card's boxes typed or ticked; the preview follows.</summary>
    private void Set(EndpointCard card, string field, ChangeEventArgs e)
    {
        var text = e.Value?.ToString() ?? string.Empty;
        switch (field)
        {
            case nameof(EndpointCard.Method):
                card.Method = text.Length > 0 ? text : "GET";
                break;
            case nameof(EndpointCard.Path):
                card.Path = text;
                break;
            case nameof(EndpointCard.Parameters):
                card.Parameters = text;
                break;
            case nameof(EndpointCard.Table):
                card.Table = e.Value is true;
                break;
            default:
                card.Columns = text;
                break;
        }
        Later();
    }

    private void BaseTyped(ChangeEventArgs e)
    {
        _baseUrl = e.Value?.ToString() ?? string.Empty;
        Later();
    }
}
