import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../account/account_screen.dart';
import '../catalog/catalog_screen.dart';
import '../drama_detail/drama_detail_screen.dart';
import '../splash/splash_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final selectedDrama =
        runtime.catalog.isNotEmpty ? runtime.catalog.first : null;
    final pages = [
      _HomeTab(flavor: widget.flavor),
      CatalogScreen(flavor: widget.flavor, catalog: runtime.catalog),
      DramaDetailScreen(
        flavor: widget.flavor,
        dramaId: selectedDrama?.dramaId ?? 'drama_1',
        drama: selectedDrama,
      ),
      AccountScreen(flavor: widget.flavor),
    ];

    return Scaffold(
      body: SafeArea(child: pages[index]),
      bottomNavigationBar: NavigationBar(
        backgroundColor: tokens.surface,
        indicatorColor: tokens.primary.withValues(alpha: 0.18),
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.home_outlined),
            label: strings.home,
          ),
          NavigationDestination(
            icon: const Icon(Icons.grid_view_outlined),
            label: strings.catalog,
          ),
          NavigationDestination(
            icon: const Icon(Icons.local_movies_outlined),
            label: strings.theater,
          ),
          NavigationDestination(
            icon: const Icon(Icons.person_outline),
            label: strings.mine,
          ),
        ],
      ),
    );
  }
}

class _HomeTab extends StatelessWidget {
  const _HomeTab({required this.flavor});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final featuredDrama =
        runtime.catalog.isNotEmpty ? runtime.catalog.first : null;
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(child: SplashHeader(flavor: flavor)),
        SliverPadding(
          padding: const EdgeInsets.all(16),
          sliver: SliverList.list(
            children: [
              Text(
                tokens.homeHeadline,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                tokens.dramaHook,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              if (runtime.loading) ...[
                const SizedBox(height: 10),
                const LinearProgressIndicator(minHeight: 3),
              ],
              if (runtime.error != null) ...[
                const SizedBox(height: 10),
                Text(
                  strings.tenantEdgeOfflineDemo,
                  style: TextStyle(
                    color: tokens.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
              const SizedBox(height: 14),
              TextField(
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  hintText: strings.searchDrama,
                  filled: true,
                  fillColor: tokens.surface,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(tokens.radius),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              _HeroBanner(flavor: flavor, drama: featuredDrama),
              const SizedBox(height: 18),
              _TemplateQuickActions(flavor: flavor),
              const SizedBox(height: 18),
              Text(
                strings.hotPicks,
                style: Theme.of(
                  context,
                ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 12),
              _DramaRail(flavor: flavor, catalog: runtime.catalog),
              const SizedBox(height: 18),
              FilledButton(
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => DramaDetailScreen(
                        flavor: flavor,
                        dramaId: featuredDrama?.dramaId ?? 'drama_1',
                        drama: featuredDrama,
                      ),
                    ),
                  );
                },
                child: Text(strings.startWatching),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _HeroBanner extends StatelessWidget {
  const _HeroBanner({required this.flavor, required this.drama});

  final FlavorConfig flavor;
  final CatalogDrama? drama;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final title = drama?.title ?? 'Seed Drama';
    final readyCount = drama?.readyEpisodeCount ?? 1;
    return Container(
      height: tokens.name == 'Vertical Pulse' ? 420 : 190,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [tokens.posterTint, tokens.primary, tokens.secondary],
        ),
        borderRadius: BorderRadius.circular(tokens.radius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          Text(
            tokens.name,
            style: TextStyle(
              color: tokens.onMedia.withValues(alpha: 0.78),
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  color: tokens.onMedia,
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 6),
          Text(
            '$readyCount episodes ready · ${tokens.playerModeLabel}',
            style: TextStyle(color: tokens.onMedia.withValues(alpha: 0.78)),
          ),
        ],
      ),
    );
  }
}

class _TemplateQuickActions extends StatelessWidget {
  const _TemplateQuickActions({required this.flavor});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final capabilities = runtime.effectiveCapabilities;
    final tokens = templateTokensFor(
      capabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final paymentProviders = capabilities.visiblePaymentProviders;
    final paymentLabels = paymentProviders.isEmpty
        ? runtime.strings.paymentsGated
        : paymentProviders.length > 2
            ? runtime.strings.paymentMethods(paymentProviders.length)
            : paymentProviders
                .map((provider) => provider.wireValue.replaceAll('_', ' '))
                .join(' / ');
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        _ActionChip(
          label: tokens.name,
          icon: Icons.dashboard_customize_outlined,
          tokens: tokens,
        ),
        _ActionChip(
          label: capabilities.storeComplianceMode.wireValue.replaceAll(
            '_',
            ' ',
          ),
          icon: Icons.verified_user_outlined,
          tokens: tokens,
        ),
        _ActionChip(
          label: paymentLabels,
          icon: Icons.account_balance_wallet_outlined,
          tokens: tokens,
        ),
      ],
    );
  }
}

class _ActionChip extends StatelessWidget {
  const _ActionChip({
    required this.label,
    required this.icon,
    required this.tokens,
  });

  final String label;
  final IconData icon;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: tokens.surface,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: tokens.primary.withValues(alpha: 0.22)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: tokens.primary),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }
}

class _DramaRail extends StatelessWidget {
  const _DramaRail({required this.flavor, required this.catalog});

  final FlavorConfig flavor;
  final List<CatalogDrama> catalog;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final items = catalog.isEmpty
        ? const [
            CatalogDrama(
              dramaId: 'drama_1',
              title: 'Seed Drama',
              posterUrl: '/assets/posters/1.png',
              episodeCount: 1,
              readyEpisodeCount: 1,
              pointPrice: 2,
            ),
          ]
        : catalog;
    return SizedBox(
      height: 176,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final drama = items[index % items.length];
          return SizedBox(
            width: 112,
            child: InkWell(
              borderRadius: BorderRadius.circular(tokens.radius),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => DramaDetailScreen(
                    flavor: flavor,
                    dramaId: drama.dramaId,
                    drama: drama,
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: tokens.posterTint,
                        borderRadius: BorderRadius.circular(tokens.radius),
                      ),
                      child: Center(
                        child: Icon(
                          tokens.name == 'Vertical Pulse'
                              ? Icons.swipe_vertical_rounded
                              : Icons.play_arrow_rounded,
                          size: 38,
                          color: tokens.primary,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    drama.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    runtime.strings.episodesReady(drama.readyEpisodeCount),
                    style: const TextStyle(fontSize: 12, color: Colors.black54),
                  ),
                ],
              ),
            ),
          );
        },
        separatorBuilder: (context, index) => const SizedBox(width: 12),
        itemCount: items.length,
      ),
    );
  }
}
