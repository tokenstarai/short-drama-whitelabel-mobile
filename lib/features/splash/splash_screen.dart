import 'package:flutter/material.dart';

import '../../app/app_runtime.dart';
import '../../flavor/flavor.dart';
import '../../theme/template_theme.dart';
import '../../theme/template_visuals.dart';

class SplashHeader extends StatelessWidget {
  const SplashHeader({required this.flavor, super.key});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    final runtime = AppRuntimeScope.of(context);
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    final dark = tokens.background.computeLuminance() < 0.25;
    final isCoolShow = tokens.name == 'CoolShow Short';
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 8),
      child: Row(
        children: [
          Container(
            width: isCoolShow ? 38 : 44,
            height: isCoolShow ? 38 : 44,
            decoration: BoxDecoration(
              gradient: isCoolShow
                  ? const LinearGradient(
                      colors: [Color(0xFF151A24), Color(0xFF0A0D14)],
                    )
                  : LinearGradient(
                      colors: [tokens.primary, tokens.secondary],
                    ),
              borderRadius: BorderRadius.circular(isCoolShow ? 12 : 14),
              boxShadow: [
                BoxShadow(
                  color: tokens.primary.withValues(alpha: 0.24),
                  blurRadius: 18,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            clipBehavior: Clip.antiAlias,
            child: isCoolShow
                ? Image.asset(
                    'assets/visuals/coolshow-mark.png',
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const Icon(
                      Icons.play_arrow_rounded,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.play_arrow_rounded, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  runtime.appName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: dark ? Colors.white : null,
                        fontWeight: FontWeight.w900,
                      ),
                ),
                Text(
                  templateHeroKicker(tokens),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: dark ? Colors.white70 : Colors.black54,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
