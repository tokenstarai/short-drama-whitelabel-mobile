import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../core/api/app_models.dart';
import '../../core/i18n/app_strings.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../../theme/template_visuals.dart';
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
      backgroundColor: tokens.background,
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
    final dark = tokens.background.computeLuminance() < 0.25;
    if (tokens.name == 'CoolShow Short') {
      return _CoolShowHomeTab(flavor: flavor);
    }
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(child: SplashHeader(flavor: flavor)),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 18),
          sliver: SliverList.list(
            children: [
              SizedBox(
                height: 38,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemBuilder: (context, index) {
                    final tab = templateTabs(tokens)[index];
                    final selected = index == 0;
                    return Container(
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                      decoration: BoxDecoration(
                        color: selected
                            ? tokens.primary
                            : tokens.surface.withValues(alpha: dark ? 0.1 : 1),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: selected
                              ? tokens.primary
                              : tokens.primary.withValues(alpha: 0.14),
                        ),
                      ),
                      child: Text(
                        tab,
                        style: TextStyle(
                          color: selected
                              ? Colors.white
                              : dark
                                  ? Colors.white70
                                  : const Color(0xFF1F2937),
                          fontWeight: FontWeight.w900,
                          fontSize: 13,
                        ),
                      ),
                    );
                  },
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemCount: templateTabs(tokens).length,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                tokens.homeHeadline,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: dark ? Colors.white : null,
                      fontWeight: FontWeight.w800,
                    ),
              ),
              const SizedBox(height: 6),
              Text(
                tokens.dramaHook,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: dark ? Colors.white70 : Colors.black54,
                    ),
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
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  hintText: strings.searchDrama,
                  filled: true,
                  fillColor: tokens.surface.withValues(alpha: dark ? 0.92 : 1),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(tokens.radius),
                    borderSide: BorderSide.none,
                  ),
                ),
                onSubmitted: (value) {
                  final query = value.trim();
                  if (query.isEmpty) {
                    return;
                  }
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => Scaffold(
                        body: SafeArea(
                          child: CatalogScreen(
                            flavor: flavor,
                            catalog: runtime.catalog,
                            initialQuery: query,
                          ),
                        ),
                      ),
                    ),
                  );
                },
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
                ).textTheme.titleLarge?.copyWith(
                      color: dark ? Colors.white : null,
                      fontWeight: FontWeight.w900,
                    ),
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

class _CoolShowHomeTab extends StatelessWidget {
  const _CoolShowHomeTab({required this.flavor});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final strings = runtime.strings;
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final catalog = runtime.catalog;
    final featuredDrama = catalog.isNotEmpty ? catalog.first : null;
    final heroTitle = featuredDrama?.title ?? 'Contract Wife';
    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: SizedBox(
            height: 456,
            child: Stack(
              fit: StackFit.expand,
              children: [
                DramaSceneBackdrop(
                  tokens: tokens,
                  title: heroTitle,
                  index: 0,
                  imageUrl: demoSceneUrl(heroTitle, 0),
                  overlay: false,
                ),
                const DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Color(0xCC06070A),
                        Color(0x3306070A),
                        Color(0xF006070A),
                      ],
                      stops: [0, 0.46, 1],
                    ),
                  ),
                ),
                Positioned(
                  left: 16,
                  right: 16,
                  top: 16,
                  child: Row(
                    children: [
                      Image.asset(
                        'assets/visuals/coolshow-mark.png',
                        width: 32,
                        height: 32,
                        fit: BoxFit.contain,
                      ),
                      const SizedBox(width: 8),
                      const Expanded(
                        child: Text(
                          'CoolShow Short',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0,
                          ),
                        ),
                      ),
                      InkWell(
                        borderRadius: BorderRadius.circular(999),
                        onTap: () => _showHomeLanguagePicker(
                          context,
                          runtime,
                        ),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.36),
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.12),
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.public_rounded,
                                color: Colors.white,
                                size: 14,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                AppStrings.languageKey(runtime.localeCode)
                                    .toUpperCase(),
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: strings.searchDrama,
                        onPressed: () => _openCatalogSearch(
                          context,
                          flavor,
                          runtime,
                        ),
                        icon: const Icon(Icons.search, color: Colors.white),
                      ),
                    ],
                  ),
                ),
                Positioned(
                  left: 16,
                  right: 16,
                  bottom: 22,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        heroTitle,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 42,
                          height: 0.95,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        featuredDrama?.summary ??
                            'A fake marriage. A real betrayal.',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.82),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        templatePrimaryMetric(tokens, featuredDrama),
                        style: TextStyle(
                          color: tokens.primary,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: 152,
                        child: FilledButton.icon(
                          style: FilledButton.styleFrom(
                            backgroundColor: tokens.primary,
                            foregroundColor: const Color(0xFF160F05),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => DramaDetailScreen(
                                flavor: flavor,
                                dramaId: featuredDrama?.dramaId ?? 'drama_1',
                                drama: featuredDrama,
                              ),
                            ),
                          ),
                          icon: const Icon(Icons.play_arrow_rounded),
                          label: Text(strings.startWatching),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 28),
          sliver: SliverList.list(
            children: [
              const _CoolShowSectionHeader(
                  title: 'Continue Watching', action: 'See all'),
              const SizedBox(height: 10),
              _CoolShowContinueRail(flavor: flavor, catalog: catalog),
              const SizedBox(height: 18),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (final tab in templateTabs(tokens).take(3)) ...[
                      _CoolShowFilterChip(
                        label: tab,
                        selected: tab == templateTabs(tokens).first,
                        tokens: tokens,
                      ),
                      const SizedBox(width: 8),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 18),
              const _CoolShowSectionHeader(
                  title: 'Trending Now', action: 'More'),
              const SizedBox(height: 10),
              _CoolShowPosterGrid(flavor: flavor, catalog: catalog),
            ],
          ),
        ),
      ],
    );
  }
}

class _CoolShowSectionHeader extends StatelessWidget {
  const _CoolShowSectionHeader({required this.title, required this.action});

  final String title;
  final String action;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
        Text(
          action,
          style: const TextStyle(
            color: Color(0xFF9AA3B2),
            fontWeight: FontWeight.w800,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}

void _openCatalogSearch(
  BuildContext context,
  FlavorConfig flavor,
  AppRuntime runtime, {
  String initialQuery = '',
}) {
  Navigator.of(context).push(
    MaterialPageRoute(
      builder: (_) => Scaffold(
        body: SafeArea(
          child: CatalogScreen(
            flavor: flavor,
            catalog: runtime.catalog,
            initialQuery: initialQuery,
          ),
        ),
      ),
    ),
  );
}

Future<void> _showHomeLanguagePicker(
  BuildContext context,
  AppRuntime runtime,
) {
  final strings = runtime.strings;
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (context) {
      return SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Text(
              strings.language,
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 8),
            for (final locale in runtime.supportedLocaleCodes)
              ListTile(
                leading: const Icon(Icons.translate_outlined),
                title: Text(AppStrings.languageNameFor(locale)),
                subtitle: Text(locale),
                trailing: locale == runtime.localeCode
                    ? const Icon(Icons.check_circle)
                    : null,
                onTap: () {
                  runtime.setLocale(locale);
                  Navigator.of(context).pop();
                },
              ),
          ],
        ),
      );
    },
  );
}

class _CoolShowContinueRail extends StatelessWidget {
  const _CoolShowContinueRail({required this.flavor, required this.catalog});

  final FlavorConfig flavor;
  final List<CatalogDrama> catalog;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final items = catalog.isEmpty ? runtime.data.catalog : catalog;
    return SizedBox(
      height: 128,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final drama = items[index];
          return SizedBox(
            width: 128,
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
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
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Image.asset(
                            demoSceneUrl(drama.title, index),
                            fit: BoxFit.cover,
                          ),
                          const DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [Colors.transparent, Colors.black87],
                              ),
                            ),
                          ),
                          Positioned(
                            left: 8,
                            right: 8,
                            bottom: 8,
                            child: Text(
                              'Ep. ${drama.readyEpisodeCount}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ),
                          Center(
                            child: Icon(
                              Icons.play_circle_fill_rounded,
                              color: tokens.primary,
                              size: 30,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    drama.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _CoolShowFilterChip extends StatelessWidget {
  const _CoolShowFilterChip({
    required this.label,
    required this.selected,
    required this.tokens,
  });

  final String label;
  final bool selected;
  final TemplateTokens tokens;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: selected ? tokens.primary : Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: selected ? const Color(0xFF171008) : Colors.white,
          fontSize: 12,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _CoolShowPosterGrid extends StatelessWidget {
  const _CoolShowPosterGrid({required this.flavor, required this.catalog});

  final FlavorConfig flavor;
  final List<CatalogDrama> catalog;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final items = catalog.isEmpty ? runtime.data.catalog : catalog;
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        childAspectRatio: 0.56,
        crossAxisSpacing: 10,
        mainAxisSpacing: 12,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final drama = items[index];
        return InkWell(
          borderRadius: BorderRadius.circular(16),
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
                child: DramaPosterCard(
                  tokens: tokens,
                  title: drama.title,
                  imageUrl: drama.posterUrl,
                  index: index,
                  compact: true,
                  rank: index + 1,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                drama.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: 11,
                ),
              ),
              Text(
                '${drama.readyEpisodeCount} eps',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Color(0xFF8D95A3), fontSize: 10),
              ),
            ],
          ),
        );
      },
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
    final isPulse = tokens.name == 'Vertical Pulse';
    final dark = tokens.background.computeLuminance() < 0.25;
    return SizedBox(
      height: isPulse ? 460 : 392,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(tokens.radius),
        child: DramaSceneBackdrop(
          tokens: tokens,
          title: title,
          index: 0,
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 9,
                          vertical: 5,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.16),
                          borderRadius: BorderRadius.circular(999),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.18),
                          ),
                        ),
                        child: Text(
                          templateHeroKicker(tokens),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ),
                    const Spacer(),
                    Icon(
                      isPulse
                          ? Icons.swipe_vertical_rounded
                          : Icons.local_fire_department_rounded,
                      color: Colors.white,
                    ),
                  ],
                ),
                const Spacer(),
                if (!isPulse)
                  Align(
                    alignment: Alignment.centerRight,
                    child: SizedBox(
                      width: 92,
                      child: DramaPosterCard(
                        tokens: tokens,
                        title: title,
                        index: 0,
                        compact: true,
                      ),
                    ),
                  ),
                const Spacer(),
                Text(
                  tokens.name,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.78),
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w900,
                        height: 1.03,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  templatePrimaryMetric(tokens, drama),
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.78),
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: dark ? Colors.black : tokens.primary,
                          visualDensity: VisualDensity.compact,
                        ),
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => DramaDetailScreen(
                              flavor: flavor,
                              dramaId: drama?.dramaId ?? 'drama_1',
                              drama: drama,
                            ),
                          ),
                        ),
                        icon: const Icon(Icons.play_arrow_rounded),
                        label: Text(
                          AppRuntimeScope.of(context).strings.startWatching,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Icon(
                      Icons.favorite_border_rounded,
                      color: Colors.white.withValues(alpha: 0.86),
                    ),
                    const SizedBox(width: 12),
                    Icon(
                      Icons.bookmark_border_rounded,
                      color: Colors.white.withValues(alpha: 0.86),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
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
      height: 236,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final drama = items[index % items.length];
          return SizedBox(
            width: 124,
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
                  DramaPosterCard(
                    tokens: tokens,
                    title: drama.title,
                    index: index + 1,
                    rank: index + 1,
                    meta:
                        '${drama.readyEpisodeCount}/${drama.episodeCount} · ${drama.pointPrice} coins',
                    onTap: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => DramaDetailScreen(
                          flavor: flavor,
                          dramaId: drama.dramaId,
                          drama: drama,
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
                    style: TextStyle(
                      fontSize: 12,
                      color: tokens.background.computeLuminance() < 0.25
                          ? Colors.white60
                          : Colors.black54,
                    ),
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
