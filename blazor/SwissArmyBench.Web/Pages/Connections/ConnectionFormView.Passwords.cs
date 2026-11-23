using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Connections;

/// <summary>The form's passwords (design principle 12.7): each one box, a variable on its own or a typed password,
/// never part of one; a typed one kept as a keyring variable on Save, the code then asking for that variable.</summary>
public partial class ConnectionFormView
{
    private const string VaultOnly = "vault only";

    /// <summary>The typed passwords, as the server takes them for a Test (never a variable's reference).</summary>
    private Dictionary<string, string> Typed() => _passwords
        .Where(p => p.Typed)
        .ToDictionary(p => p.Secret, p => PasswordBox.TypedValue(p.Text));

    private string PasswordPlaceholder(PasswordBox box) =>
        _form?.Summary?.Secrets?.GetValueOrDefault(box.Secret) == true ? "Saved"
        : _form?.SecretsFrom == VaultOnly ? PasswordBox.Named("VARIABLE")
        : string.Empty;

    private string VariableFor(PasswordBox box) =>
        PasswordBox.VariableFor(_name.Trim().Length > 0 ? _name.Trim() : _form?.Label ?? string.Empty, box.Label);

    /// <summary>A box left or changed: a variable on its own points the code at it; a typed password waits for Save.</summary>
    private async Task SettleAsync(PasswordBox box)
    {
        if (box.Text == box.Settled)
        {
            return;
        }
        box.Settled = box.Text;
        var variable = PasswordBox.ReferenceOnly(box.Text);
        if (variable is null && PasswordBox.NamesVariable(box.Text))
        {
            var label = ConnectionWords.Words(box.Label);
            _error = new ApiException(0, new Refusal($"{label} takes one variable on its own, such as {PasswordBox.Named(VariableFor(box))}, or a typed password.", label), string.Empty);
            return;
        }
        if (variable is not null && variable != box.Secret)
        {
            try
            {
                await PointAtAsync(box, variable);
                _error = null;
            }
            catch (ApiException error)
            {
                Failed(error);
            }
        }
    }

    /// <summary>The code's password pointed at a variable (secret("NAME")); the box follows the secret's new name.</summary>
    private async Task PointAtAsync(PasswordBox box, string variable)
    {
        await _turn.WaitAsync();
        try
        {
            var answer = await Connections.PointAtAsync(_code, box.Secret, variable);
            _code = answer.Code;
            box.Secret = answer.Secret;
        }
        finally
        {
            _turn.Release();
        }
    }

    /// <summary>Before Save: each typed password kept as a keyring variable, the code then asking for that variable.</summary>
    private async Task TypedToVariablesAsync()
    {
        if (_form?.SecretsFrom == VaultOnly)
        {
            return; // refused by the server, said there
        }
        foreach (var box in _passwords.Where(p => p.Typed).ToList())
        {
            var variable = VariableFor(box);
            await Connections.KeepInKeyringAsync(variable, PasswordBox.TypedValue(box.Text));
            await PointAtAsync(box, variable);
            box.Text = PasswordBox.Named(variable);
            box.Settled = box.Text;
        }
    }
}
