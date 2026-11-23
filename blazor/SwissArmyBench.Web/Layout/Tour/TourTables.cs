using System.Globalization;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Layout.Tour;

/// <summary>
/// The tour's two small made-up tables (the classic tour.ts stage): customers and their orders sharing customer_id,
/// pasted as the page's Ctrl+V pastes them (POST /datasets/{name}/paste), named so they never take an open table's
/// name. Each one opened is told at once, so a close while staging still closes it.
/// </summary>
public sealed record TourTables(TourTable Orders, TourTable Customers)
{
    private const int OrderCount = 12;
    private const int FirstOrder = 1001;
    private const int CustomerStride = 5;
    private const int AmountStride = 37;
    private const int AmountSpread = 90;
    private const double AmountBase = 12.5;
    private const int QuantitySpread = 4;
    private const int MonthSpread = 9;
    private const int FirstDay = 10;

    private static readonly string[] _customers =
        ["Ada Fernwood", "Bo Calder", "Cy Marlow", "Dee Ashby", "Eli Brook", "Fay Linden", "Gus Harrow", "Hal Penrose", "Ivy Tamsin", "Jo Quill", "Kit Rowan", "Lu Merrin"];

    private static readonly string[] _cities = ["Northvale", "Easton Cove", "Westmere", "Southby"];
    private static readonly string[] _products = ["Anvil", "Bolt", "Cog", "Dowel"];

    /// <summary>Tab-separated text, as Excel copies it.</summary>
    public static string CustomersText() =>
        Lines(["customer_id\tname\tcity", .. _customers.Select((name, i) => $"{i + 1}\t{name}\t{_cities[i % _cities.Length]}")]);

    public static string OrdersText() =>
        Lines(["order_id\tcustomer_id\tproduct\tquantity\tamount\torder_date",
            .. Enumerable.Range(0, OrderCount).Select(i => string.Join('\t',
                FirstOrder + i,
                (i * CustomerStride % _customers.Length) + 1,
                _products[i % _products.Length],
                (i % QuantitySpread) + 1,
                ((i * AmountStride % AmountSpread) + AmountBase).ToString(CultureInfo.InvariantCulture),
                $"2026-0{(i % MonthSpread) + 1}-{FirstDay + i}"))]);

    /// <summary>Both tables opened, or null when a paste was refused (the cards that need them say "not here").</summary>
    public static async Task<TourTables?> StageAsync(ApiClient api, Action<string> opened)
    {
        try
        {
            var taken = (await api.GetAsync<DatasetsAnswer>("/datasets")).Datasets.Select(d => d.Name).ToHashSet();
            var customers = await PasteAsync(api, FreeName("tour_customers", taken), CustomersText());
            opened(customers.Dataset);
            var orders = await PasteAsync(api, FreeName("tour_orders", taken), OrdersText());
            opened(orders.Dataset);
            return new TourTables(orders, customers);
        }
        catch (ApiException)
        {
            return null;
        }
    }

    /// <summary>A name no open table has: base, else base_2, base_3...</summary>
    public static string FreeName(string name, ISet<string> taken)
    {
        var free = Enumerable.Range(2, taken.Count + 1).Select(n => $"{name}_{n}").Prepend(name).First(n => !taken.Contains(n));
        taken.Add(free);
        return free;
    }

    private static async Task<TourTable> PasteAsync(ApiClient api, string name, string text)
    {
        var made = await api.PostTextAsync<MadeTable>($"/datasets/{ApiClient.Part(name)}/paste", text);
        return new TourTable(made.Dataset ?? name, made.Grid ?? string.Empty);
    }

    private static string Lines(IEnumerable<string> rows) => string.Join('\n', rows) + "\n";
}
